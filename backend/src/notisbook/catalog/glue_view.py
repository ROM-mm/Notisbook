"""Projeção só leitura do catálogo `glue` para o painel Catalog (árvore, Table info e Catalog info).

Converte o payload do AWS Glue guardado em `glue_*` para o mesmo envelope que `registry` e `iceberg_jdbc` devolvem,
sem kernel. A location sai como foi gravada (`s3://...`), não na forma canônica `s3a`. Valores sensíveis dos
parâmetros saem mascarados por `catalog_info.redact`. `sqlite3.Error` sobe ao chamador (JSON ilegível vira `sqlite3.DatabaseError` no Table info).
"""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from ..notislake import locations
from . import glue_repo
from .catalog_info import STATUS_EMPTY, STATUS_OK, redact
from .registry import MAX_TABLES, folder_in_use

GLUE_CATALOG = glue_repo.GLUE_CATALOG
ERR_UNREADABLE = "glue_catalog_unreadable"
FORMAT_UNKNOWN = "unknown"
FORMAT_ICEBERG = "iceberg"
FORMAT_DELTA = "delta"
FORMAT_HUDI = "hudi"
TYPE_MANAGED = "MANAGED"
TYPE_EXTERNAL = "EXTERNAL"
# Mesmos valores de `registry` e `iceberg_jdbc`; a regra de cada um está na docstring de `_drop_behavior`.
DROP_DELETES_FILES = "deletes_files"
DROP_REGISTRY_ONLY = "registry_only"
DROP_KEEPS_OUTSIDE = "keeps_files_outside_managed"
DROP_KEEPS_SHARED = "keeps_files_shared"
# Onde está o schema real: o Delta guarda só um placeholder no Glue e o schema fica no `_delta_log`.
SCHEMA_STORAGE_DESCRIPTOR = "storage_descriptor"
SCHEMA_SPARK_PROPERTIES = "spark_properties"
SCHEMA_DELTA_LOG = "delta_log"
_SCHEMA_PARTS = "spark.sql.sources.schema.part."
VERSION_KIND = "glue_version"

# Consulta leve por tabela: só os campos de que a árvore e o resumo precisam, sem carregar o StorageDescriptor inteiro.
_NODE_FIELDS = (
    "name, description, json_extract(storage_descriptor, '$.Location'), "
    "json_extract(parameters, '$.classification'), json_extract(parameters, '$.\"spark.sql.sources.provider\"'), "
    "json_extract(storage_descriptor, '$.InputFormat'), json_extract(storage_descriptor, '$.SerdeInfo.SerializationLibrary'), "
    "table_type, json_extract(parameters, '$.table_type')"
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


def _format(classification: Any, provider: Any, input_format: Any, serde: Any, iceberg_type: Any = None) -> str:
    """Iceberg (`table_type=ICEBERG`) e provider Delta/Hudi primeiro; depois `classification`, provider e SerDe/InputFormat."""
    if (_text(iceberg_type) or "").upper() == "ICEBERG":
        return FORMAT_ICEBERG
    if (_text(provider) or "").lower() in (FORMAT_DELTA, FORMAT_HUDI):
        return str(_text(provider)).lower()
    for hint in (classification, provider):
        if _text(hint):
            return str(_text(hint)).lower()
    blob = f"{_text(input_format) or ''} {_text(serde) or ''}".lower()
    return next((fmt for key, fmt in _SERDE_HINTS if key in blob), FORMAT_UNKNOWN)


def _kind(glue_table_type: Any) -> str:
    return TYPE_MANAGED if glue_table_type == "MANAGED_TABLE" else TYPE_EXTERNAL


def _drop_behavior(conn: sqlite3.Connection, fmt: str, kind: str, database: str, table: str, location: Any) -> str:
    """O que o DROP faz com os arquivos na própria pasta gerenciada (`glue_repo.owns_folder`).

    A `MANAGED_TABLE` tem a pasta apagada pelo Hive do kernel mesmo em uso por outra tabela (`deletes_files`). O Iceberg
    (EXTERNAL) só tem a pasta apagada se nenhuma outra a usa. Fora da própria pasta, a MANAGED é EXTERNAL de fato para o
    Notisbook (`keeps_files_outside_managed`) e a externa só sai do registro.
    """
    managed = kind == TYPE_MANAGED
    iceberg = fmt == FORMAT_ICEBERG
    own_location = location if isinstance(location, str) else None
    if not glue_repo.owns_folder(database, table, own_location, managed=managed, iceberg=iceberg):
        return DROP_KEEPS_OUTSIDE if managed else DROP_REGISTRY_ONLY
    if not managed and folder_in_use(conn, locations.canonical(location).rstrip("/"), skip_tables=[(GLUE_CATALOG, database, table)]):
        return DROP_KEEPS_SHARED
    return DROP_DELETES_FILES


def _shown_location(recorded: Any, canonical: str | None = None) -> str | None:
    """Location como gravada, sem userinfo de URI; sem ela, a canônica (se houver)."""
    raw = _text(recorded) or canonical
    return None if raw is None else redact("location", raw)[0]


def _iso(epoch: Any) -> str | None:
    if not isinstance(epoch, (int, float)):
        return None
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds")


def _node(database: str, row: tuple[Any, ...]) -> dict[str, Any]:
    name, description, location, classification, provider, input_format, serde, glue_type, iceberg_type = row
    return {
        "name": name,
        "namespace": [database],
        "format": _format(classification, provider, input_format, serde, iceberg_type),
        "table_type": _kind(glue_type),
        "is_temporary": False,
        "location": _shown_location(location),
        # O bucket não é sondado na listagem (mesma regra do Iceberg em s3a).
        "available": None,
        "description": description,
    }


def _database_names(conn: sqlite3.Connection) -> list[str]:
    """Databases por nome."""
    return sorted(r[0] for r in conn.execute("SELECT name FROM glue_databases"))


def empty_databases() -> list[dict[str, Any]]:
    """Nó sem `catalog.db`: nenhum database, pois um catalog.db novo é quem semeia os iniciais."""
    return []


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
    return {"namespaces": [], "tables": 0, "views": 0, "formats": {}}


def catalog_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Contagens exatas (sem teto) por database e por formato; o `glue` não tem views."""
    if not _has_tables(conn):
        return _empty_summary()
    per_db: dict[str, int] = {}
    formats: dict[str, int] = {}
    for database, *row in conn.execute(f"SELECT database_name, {_NODE_FIELDS} FROM glue_tables"):
        per_db[database] = per_db.get(database, 0) + 1
        fmt = _format(row[3], row[4], row[5], row[6], row[8])
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
        "warehouse": f"s3://{locations.MANAGED_BUCKET}",
        "uri": None,
        "file_io": None,
        "counts": {"namespaces": len(namespaces), "tables": summary["tables"], "views": 0},
        "formats": summary["formats"],
        "namespaces": namespaces,
        "namespaces_truncated": False,
        "config": config,
    }


def _spark_type(spec: Any) -> str:
    """Tipo do schema JSON do Spark (string ou objeto aninhado) na notação do Hive."""
    if isinstance(spec, str):
        return spec
    if not isinstance(spec, dict):
        return ""
    kind = spec.get("type")
    if kind == "struct":
        fields = spec.get("fields")
        inner = ",".join(f"{f.get('name')}:{_spark_type(f.get('type'))}" for f in fields if isinstance(f, dict)) if isinstance(fields, list) else ""
        return f"struct<{inner}>"
    if kind == "array":
        return f"array<{_spark_type(spec.get('elementType'))}>"
    if kind == "map":
        return f"map<{_spark_type(spec.get('keyType'))},{_spark_type(spec.get('valueType'))}>"
    return str(kind or "")


def _field_comment(field: dict[str, Any]) -> Any:
    metadata = field.get("metadata")
    return metadata.get("comment") if isinstance(metadata, dict) else None


def _spark_schema_columns(parameters: dict[str, str]) -> list[dict[str, Any]]:
    """Colunas de `spark.sql.sources.schema.part.N` (como o Hudi as grava); vazio se ausente ou ilegível."""
    parts = []
    index = 0
    while (chunk := parameters.get(f"{_SCHEMA_PARTS}{index}")) is not None:
        parts.append(chunk)
        index += 1
    if not parts:
        return []
    try:
        schema = json.loads("".join(parts))
    except ValueError:
        return []
    fields = schema.get("fields") if isinstance(schema, dict) else None
    return [
        {"Name": f["name"], "Type": _spark_type(f.get("type")), "Comment": _field_comment(f)}
        for f in fields or []
        if isinstance(f, dict) and f.get("name")
    ]


def _schema_source(fmt: str, table: dict[str, Any]) -> str:
    """De onde vêm `columns`: Delta não tem schema no Glue; Hudi sem `Columns` usa as propriedades do Spark."""
    if fmt == FORMAT_DELTA:
        return SCHEMA_DELTA_LOG
    if fmt == FORMAT_HUDI and not table["StorageDescriptor"].get("Columns") and _spark_schema_columns(table["Parameters"]):
        return SCHEMA_SPARK_PROPERTIES
    return SCHEMA_STORAGE_DESCRIPTOR


def _columns(table: dict[str, Any], source: str = SCHEMA_STORAGE_DESCRIPTOR) -> list[dict[str, Any]]:
    """Colunas do schema (StorageDescriptor ou propriedades Spark) seguidas das partition keys (o Glue as guarda fora de `Columns`).

    No Delta o `Columns` é só um placeholder: ficam apenas as partition keys.
    """
    out: list[dict[str, Any]] = []
    keys = table["PartitionKeys"]
    names = {c.get("Name") for c in keys if isinstance(c, dict)}
    if source == SCHEMA_SPARK_PROPERTIES:
        body = [c for c in _spark_schema_columns(table["Parameters"]) if c["Name"] not in names]
    elif source == SCHEMA_DELTA_LOG:
        body = []
    else:
        body = table["StorageDescriptor"].get("Columns")
    for items, is_partition in ((body, False), (keys, True)):
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
        params.get("classification"),
        params.get("spark.sql.sources.provider"),
        descriptor.get("InputFormat"),
        _serde_library(descriptor),
        params.get("table_type"),
    )
    kind = _kind(raw["TableType"])
    source = _schema_source(fmt, raw)
    columns = _columns(raw, source)
    return {
        "catalog": GLUE_CATALOG,
        "database": raw["DatabaseName"],
        "table": raw["Name"],
        "format": fmt,
        "table_type": kind,
        "drop_behavior": _drop_behavior(conn, fmt, kind, raw["DatabaseName"], raw["Name"], descriptor.get("Location")),
        "location": _shown_location(descriptor.get("Location")),
        "available": None,
        "description": raw.get("Description"),
        "created_at": _iso(raw.get("CreateTime")),
        "updated_at": _iso(raw.get("UpdateTime")),
        "partition_columns": [c["name"] for c in columns if c["is_partition"]],
        "columns": columns,
        "schema_source": source,
        "version": {"kind": VERSION_KIND, "value": raw.get("VersionId")},
        "history": None,
        "properties": _properties(raw["Parameters"]),
        "stats": None,
        "metadata_error": None,
        "glue": _storage(raw),
    }
