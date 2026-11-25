"""Projeção só leitura do catálogo `glue` para o painel Catalog (árvore, Table info e Catalog info).

Converte o payload do AWS Glue guardado em `glue_*` para o mesmo envelope que `registry` e `iceberg_jdbc` devolvem,
sem kernel. A location sai como foi gravada (`s3://...`), não na forma canônica `s3a`. Valores sensíveis dos
parâmetros saem mascarados por `catalog_info.redact`. `sqlite3.Error` sobe ao chamador (JSON ilegível vira `sqlite3.DatabaseError` no Table info).
"""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from ..notislake import locations
from . import glue_repo
from .catalog_info import STATUS_EMPTY, STATUS_OK, redact
from .registry import MAX_TABLES

GLUE_CATALOG = glue_repo.GLUE_CATALOG
ERR_UNREADABLE = "glue_catalog_unreadable"
FORMAT_UNKNOWN = "unknown"
# DELETE no Glue só remove o registro, mas a semântica de DROP por formato ainda não é exposta para o `glue`.
DROP_NONE = "none"
VERSION_KIND = "glue_version"

# Consulta leve por tabela: só os campos de que a árvore e o resumo precisam, sem carregar o StorageDescriptor inteiro.
_NODE_FIELDS = (
    "name, description, json_extract(storage_descriptor, '$.Location'), "
    "json_extract(parameters, '$.classification'), json_extract(parameters, '$.\"spark.sql.sources.provider\"'), "
    "json_extract(storage_descriptor, '$.InputFormat'), json_extract(storage_descriptor, '$.SerdeInfo.SerializationLibrary')"
)
_SERDE_HINTS = (
    ("parquet", "parquet"),
    ("orcserde", "orc"),
    ("orcinputformat", "orc"),
    (".orc.", "orc"),
    ("avro", "avro"),
    ("json", "json"),
    ("opencsv", "csv"),
    ("lazysimple", "csv"),
    ("textinputformat", "csv"),
)


def _has_tables(conn: sqlite3.Connection) -> bool:
    """`catalog.db` anterior ao `glue` ainda não tem as tabelas `glue_*`: o nó aparece vazio, sem erro."""
    found = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('glue_databases', 'glue_tables')"
    ).fetchone()
    return int(found[0]) == 2


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _format(classification: Any, provider: Any, input_format: Any, serde: Any) -> str:
    """Formato pela `classification` (convenção do Glue), depois pelo provider Spark e por fim pelo SerDe/InputFormat."""
    for hint in (classification, provider):
        if _text(hint):
            return str(_text(hint)).lower()
    blob = f"{_text(input_format) or ''} {_text(serde) or ''}".lower()
    return next((fmt for key, fmt in _SERDE_HINTS if key in blob), FORMAT_UNKNOWN)


def _shown_location(recorded: Any, canonical: str | None = None) -> str | None:
    """Location como gravada, sem userinfo de URI; sem ela, a canônica (se houver)."""
    raw = _text(recorded) or canonical
    return None if raw is None else redact("location", raw)[0]


def _iso(epoch: Any) -> str | None:
    if not isinstance(epoch, (int, float)):
        return None
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds")


def _node(database: str, row: tuple[Any, ...]) -> dict[str, Any]:
    name, description, location, classification, provider, input_format, serde = row
    return {
        "name": name,
        "namespace": [database],
        "format": _format(classification, provider, input_format, serde),
        "table_type": "EXTERNAL",
        "is_temporary": False,
        "location": _shown_location(location),
        # O bucket não é sondado na listagem (mesma regra do Iceberg em s3a).
        "available": None,
        "description": description,
    }


def _database_names(conn: sqlite3.Connection) -> list[str]:
    """Databases com as camadas primeiro (ordem de `LAYERS`) e os demais por nome."""
    names = [r[0] for r in conn.execute("SELECT name FROM glue_databases")]
    return sorted(names, key=lambda n: (locations.layer_rank(n), n))


def empty_databases() -> list[dict[str, Any]]:
    """Nó sem `catalog.db`: só as camadas, que sempre existem no `glue`."""
    return [{"name": ns, "tables": []} for ns in locations.LAYERS]


def list_databases(conn: sqlite3.Connection, max_total: int) -> tuple[list[dict[str, Any]], int]:
    """Databases do `glue` com suas tabelas e o total listado; `max_total` é o que resta do teto global."""
    if not _has_tables(conn):
        return empty_databases(), 0
    used = 0
    databases: list[dict[str, Any]] = []
    for db in _database_names(conn):
        if used >= max_total:
            databases.append({"name": db, "tables": [], "truncated": True})
            continue
        limit = min(MAX_TABLES, max_total - used)
        rows = conn.execute(
            f"SELECT {_NODE_FIELDS} FROM glue_tables WHERE database_name = ? ORDER BY name LIMIT ?", (db, limit + 1)
        ).fetchall()
        entry: dict[str, Any] = {"name": db, "tables": [_node(db, r) for r in rows[:limit]]}
        if len(rows) > limit:
            entry["truncated"] = True
        used += len(entry["tables"])
        databases.append(entry)
    return databases, used


def error_entry(code: str = ERR_UNREADABLE) -> dict[str, Any]:
    """Nó degradado: o `glue` ilegível não derruba os demais catálogos."""
    return {"name": GLUE_CATALOG, "databases": [], "error": code}


def _empty_summary() -> dict[str, Any]:
    layers = [{"name": ns, "tables": 0, "views": 0} for ns in locations.LAYERS]
    return {"namespaces": layers, "tables": 0, "views": 0, "formats": {}}


def catalog_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Contagens exatas (sem teto) por database e por formato; o `glue` não tem views."""
    if not _has_tables(conn):
        return _empty_summary()
    per_db: dict[str, int] = {}
    formats: dict[str, int] = {}
    for database, *row in conn.execute(f"SELECT database_name, {_NODE_FIELDS} FROM glue_tables"):
        per_db[database] = per_db.get(database, 0) + 1
        fmt = _format(row[3], row[4], row[5], row[6])
        formats[fmt] = formats.get(fmt, 0) + 1
    names = _database_names(conn)
    return {
        "namespaces": [{"name": ns, "tables": per_db.get(ns, 0), "views": 0} for ns in names],
        "tables": sum(per_db.get(ns, 0) for ns in names),
        "views": 0,
        "formats": formats,
    }


def build_catalog_info(conn: sqlite3.Connection | None) -> dict[str, Any]:
    """Painel Catalog info do `glue` (mesmo envelope de `catalog_info.build_catalog_info`); `status: "empty"` sem tabelas `glue_*`."""
    ready = conn is not None and _has_tables(conn)
    summary = catalog_summary(conn) if conn is not None else _empty_summary()
    namespaces = summary["namespaces"]
    buckets = ", ".join(f"s3://{b}" for b in locations.known_buckets())
    config = []
    for key, value in (("glue.endpoint_path", "/glue"), ("glue.buckets", buckets)):
        shown, redacted = redact(key, value)
        config.append({"key": key, "value": shown, "redacted": redacted})
    return {
        "name": GLUE_CATALOG,
        "kind": "named",
        "backing_catalog": None,
        "status": STATUS_OK if ready else STATUS_EMPTY,
        "profile": "local",
        "implementation": "AWS Glue Data Catalog (local endpoint)",
        "type": "glue",
        "warehouse": f"s3://{locations.BUCKET}",
        "uri": None,
        "file_io": None,
        "counts": {"namespaces": len(namespaces), "tables": summary["tables"], "views": 0},
        "formats": summary["formats"],
        "namespaces": namespaces,
        "namespaces_truncated": False,
        "config": config,
    }


def _columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    """Colunas do StorageDescriptor seguidas das partition keys (o Glue as guarda fora de `Columns`)."""
    out: list[dict[str, Any]] = []
    sources = ((table["StorageDescriptor"].get("Columns"), False), (table["PartitionKeys"], True))
    for items, is_partition in sources:
        for col in items if isinstance(items, list) else []:
            if not isinstance(col, dict) or not col.get("Name"):
                continue
            out.append(
                {
                    "name": str(col["Name"]),
                    "data_type": str(col.get("Type", "")),
                    "nullable": True,
                    "is_partition": is_partition,
                    "is_bucket": False,
                    "description": col.get("Comment") if isinstance(col.get("Comment"), str) else None,
                }
            )
    return out


def _properties(parameters: dict[str, str]) -> dict[str, str]:
    return {k: redact(k, v)[0] for k, v in parameters.items()}


def _serde_library(descriptor: dict[str, Any]) -> str | None:
    serde = descriptor.get("SerdeInfo")
    return _text(serde.get("SerializationLibrary")) if isinstance(serde, dict) else None


def _storage(table: dict[str, Any]) -> dict[str, Any]:
    descriptor = table["StorageDescriptor"]
    return {
        "classification": _text(table["Parameters"].get("classification")),
        "input_format": _text(descriptor.get("InputFormat")),
        "output_format": _text(descriptor.get("OutputFormat")),
        "serde_library": _serde_library(descriptor),
        "compressed": descriptor.get("Compressed") if isinstance(descriptor.get("Compressed"), bool) else None,
        "glue_table_type": table["TableType"],
    }


def read_table_info(conn: sqlite3.Connection, database: str, table: str) -> dict[str, Any] | None:
    """Metadados de uma tabela `glue` no envelope de `registry.read_table_info`; `None` se não existir.

    Campos do envelope sem equivalente no Glue ficam `None`/vazios; `properties` são os `Parameters` (mascarados) e
    `glue` traz o que é só do Glue (classification, formatos de entrada/saída, SerDe).
    """
    if not _has_tables(conn):
        return None
    try:
        raw = glue_repo.get_table(conn, database, table)
    except glue_repo.GlueError:
        return None
    except ValueError as exc:
        # JSON ilegível no registro: o chamador trata como falha do `catalog.db` (503), não como tabela ausente.
        raise sqlite3.DatabaseError("glue table row unreadable") from exc
    descriptor = raw["StorageDescriptor"]
    params = raw["Parameters"]
    fmt = _format(
        params.get("classification"), params.get("spark.sql.sources.provider"), descriptor.get("InputFormat"), _serde_library(descriptor)
    )
    columns = _columns(raw)
    return {
        "catalog": GLUE_CATALOG,
        "database": raw["DatabaseName"],
        "table": raw["Name"],
        "format": fmt,
        "table_type": "EXTERNAL",
        "drop_behavior": DROP_NONE,
        "location": _shown_location(descriptor.get("Location")),
        "available": None,
        "description": raw.get("Description"),
        "created_at": _iso(raw.get("CreateTime")),
        "updated_at": _iso(raw.get("UpdateTime")),
        "partition_columns": [c["name"] for c in columns if c["is_partition"]],
        "columns": columns,
        "version": {"kind": VERSION_KIND, "value": raw.get("VersionId")},
        "history": None,
        "properties": _properties(raw["Parameters"]),
        "stats": None,
        "metadata_error": None,
        "glue": _storage(raw),
    }
