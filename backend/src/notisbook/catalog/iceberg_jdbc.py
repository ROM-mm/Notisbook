"""Leitura e escrita do catálogo `iceberg` (JdbcCatalog do Iceberg) direto do SQLite e dos `metadata.json`, sem Spark.

Camada de isolamento sobre o formato INTERNO do JdbcCatalog (tabelas `iceberg_*` e metadata v1/v2):
ele não é API pública. A escrita (`create_namespace`/`drop_namespace_rows`) reproduz o SQL do JdbcCatalog 1.10.1
(`createNamespace` grava `exists=true`; `dropNamespace`/`dropTable` fazem DELETE). Trocar a versão do Iceberg
na MATRIX de bundles exige rever a leitura E a escrita. A transação (`BEGIN IMMEDIATE`) pertence ao chamador.
Formato inesperado degrada só o catálogo `iceberg` (`error`), nunca o resto do painel.
"""

import json
import sqlite3
import zlib
from pathlib import Path
from typing import Any

from .registry import MAX_TABLES, is_available, local_path

ICEBERG_CATALOG = "iceberg"
ERR_UNSUPPORTED = "unsupported_iceberg_catalog_schema"
ERR_UNREADABLE = "iceberg_catalog_unreadable"
# Teto do `metadata.json` (já descomprimido): evita carregar um arquivo gigante ou uma bomba gzip.
MAX_METADATA_BYTES = 16 * 1024 * 1024
_MAX_TYPE_DEPTH = 8

_REQUIRED_COLUMNS = {
    "iceberg_tables": {"catalog_name", "table_namespace", "table_name", "metadata_location"},
    "iceberg_namespace_properties": {"catalog_name", "namespace"},
}
# Só tabelas: views do Iceberg dividem `iceberg_tables`, marcadas por `iceberg_type = 'VIEW'`.
_TABLE_FILTER = "(iceberg_type = 'TABLE' OR iceberg_type IS NULL)"


class UnsupportedIcebergSchema(Exception):
    """As tabelas `iceberg_*` não têm o formato esperado."""


class IcebergMetadataError(Exception):
    """O `metadata.json` da tabela não pôde ser lido ou interpretado."""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _check_schema(conn: sqlite3.Connection) -> bool:
    """Confere as colunas lidas; devolve se `iceberg_type` existe (opcional: sem ele não há views)."""
    for table, required in _REQUIRED_COLUMNS.items():
        if not required <= _table_columns(conn, table):
            raise UnsupportedIcebergSchema(table)
    return "iceberg_type" in _table_columns(conn, "iceberg_tables")


def _type_filter(has_type: bool) -> str:
    return f"AND {_TABLE_FILTER}" if has_type else ""


def _table_dir(metadata_location: str) -> Path | None:
    """Pasta da tabela: pai de `metadata/` no `metadata_location` (ou o próprio diretório do arquivo)."""
    path = local_path(metadata_location)
    if path is None:
        return None
    parent = path.parent
    return parent.parent if parent.name == "metadata" else parent


def _table_type(metadata_location: str, warehouse: Path, namespace: str, table: str) -> str:
    """MANAGED se a pasta é `<warehouse>/<ns…>/<t>`; informativo (o Iceberg não distingue)."""
    folder = _table_dir(metadata_location)
    if folder is None:
        return "EXTERNAL"
    expected = warehouse.joinpath(*namespace.split("."), table)
    try:
        return "MANAGED" if folder.resolve() == expected.resolve() else "EXTERNAL"
    except OSError:
        return "EXTERNAL"


def _node(row: tuple[Any, ...], warehouse: Path) -> dict[str, Any]:
    namespace, name, metadata_location = row[0], row[1], row[2] or ""
    folder = _table_dir(metadata_location)
    return {
        "name": name,
        "namespace": namespace.split("."),
        "format": "iceberg",
        "table_type": _table_type(metadata_location, warehouse, namespace, name),
        "is_temporary": False,
        "location": folder.as_uri() if folder is not None else metadata_location or None,
        "available": is_available(metadata_location),
        "description": None,
    }


def list_databases(conn: sqlite3.Connection, warehouse: Path, max_total: int) -> tuple[list[dict[str, Any]], int]:
    """Databases (namespaces) do `iceberg` e o total de tabelas listadas.

    Namespaces = união de `iceberg_namespace_properties` e `iceberg_tables`: o Iceberg só grava propriedades
    quando o namespace é criado explicitamente. Levanta `UnsupportedIcebergSchema`.
    """
    has_type = _check_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT namespace FROM iceberg_namespace_properties WHERE catalog_name = ? "
            "UNION SELECT table_namespace FROM iceberg_tables WHERE catalog_name = ?",
            (ICEBERG_CATALOG, ICEBERG_CATALOG),
        )
    }
    used = 0
    databases: list[dict[str, Any]] = []
    for db in sorted(names):
        if used >= max_total:
            databases.append({"name": db, "tables": [], "truncated": True})
            continue
        limit = min(MAX_TABLES, max_total - used)
        rows = conn.execute(
            "SELECT table_namespace, table_name, metadata_location FROM iceberg_tables "
            f"WHERE catalog_name = ? AND table_namespace = ? {_type_filter(has_type)} ORDER BY table_name LIMIT ?",
            (ICEBERG_CATALOG, db, limit + 1),
        ).fetchall()
        entry: dict[str, Any] = {"name": db, "tables": [_node(r, warehouse) for r in rows[:limit]]}
        if len(rows) > limit:
            entry["truncated"] = True
        used += len(entry["tables"])
        databases.append(entry)
    return databases, used


def check_schema(conn: sqlite3.Connection) -> bool:
    """Valida o formato antes de escrever; devolve se `iceberg_type` existe. Levanta `UnsupportedIcebergSchema`."""
    return _check_schema(conn)


def table_folder(metadata_location: str | None) -> Path | None:
    """Pasta da tabela a partir do `metadata_location` (None se não for um caminho local)."""
    return _table_dir(metadata_location or "")


# Prefixo `ns.` por `substr`: o LIKE do SQLite ignora a caixa ASCII e `A.b` casaria como filho de `a`.
_PREFIX_MATCH = "substr(namespace, 1, ?) = ?"
_PREFIX_MATCH_T = _PREFIX_MATCH.replace("namespace", "table_namespace")
_PREFIX_MATCH_FOLDED = "lower(substr(namespace, 1, ?)) = lower(?)"
_PREFIX_MATCH_FOLDED_T = _PREFIX_MATCH_FOLDED.replace("namespace", "table_namespace")


def namespace_exists(conn: sqlite3.Connection, namespace: str, *, ignore_case: bool = False) -> bool:
    """Como o `JdbcUtil.namespaceExists`: o namespace existe por linha própria ou por filhos (`ns.%`).

    `ignore_case` serve à criação, que recusa colisão só por caixa (o FS do macOS não distingue).
    """
    prefix = namespace + "."
    cmp = "lower(namespace) = lower(?)" if ignore_case else "namespace = ?"
    cmp_t = cmp.replace("namespace", "table_namespace")
    match, match_t = (_PREFIX_MATCH_FOLDED, _PREFIX_MATCH_FOLDED_T) if ignore_case else (_PREFIX_MATCH, _PREFIX_MATCH_T)
    return (
        conn.execute(
            f"SELECT 1 FROM iceberg_namespace_properties WHERE catalog_name = ? AND ({cmp} OR {match}) "
            f"UNION SELECT 1 FROM iceberg_tables WHERE catalog_name = ? AND ({cmp_t} OR {match_t}) LIMIT 1",
            (ICEBERG_CATALOG, namespace, len(prefix), prefix, ICEBERG_CATALOG, namespace, len(prefix), prefix),
        ).fetchone()
        is not None
    )


def has_child_namespaces(conn: sqlite3.Connection, namespace: str) -> bool:
    prefix = namespace + "."
    return (
        conn.execute(
            f"SELECT 1 FROM iceberg_namespace_properties WHERE catalog_name = ? AND {_PREFIX_MATCH} "
            f"UNION SELECT 1 FROM iceberg_tables WHERE catalog_name = ? AND {_PREFIX_MATCH_T} LIMIT 1",
            (ICEBERG_CATALOG, len(prefix), prefix, ICEBERG_CATALOG, len(prefix), prefix),
        ).fetchone()
        is not None
    )


def namespace_has_rows(conn: sqlite3.Connection, namespace: str) -> bool:
    """O namespace tem linha própria (propriedades ou tabelas/views), sem contar filhos."""
    return (
        conn.execute(
            "SELECT 1 FROM iceberg_namespace_properties WHERE catalog_name = ? AND namespace = ? "
            "UNION SELECT 1 FROM iceberg_tables WHERE catalog_name = ? AND table_namespace = ? LIMIT 1",
            (ICEBERG_CATALOG, namespace, ICEBERG_CATALOG, namespace),
        ).fetchone()
        is not None
    )


def create_namespace(conn: sqlite3.Connection, namespace: str) -> bool:
    """Cria o namespace como o `JdbcCatalog.createNamespace(ns, {})`; `False` se já existe. Dentro de transação."""
    if namespace_exists(conn, namespace, ignore_case=True):
        return False
    conn.execute(
        "INSERT INTO iceberg_namespace_properties (catalog_name, namespace, property_key, property_value) "
        "VALUES (?, ?, 'exists', 'true')",
        (ICEBERG_CATALOG, namespace),
    )
    return True


def namespace_entries(conn: sqlite3.Connection, namespace: str, has_type: bool) -> list[tuple[str, str, str]]:
    """`(table_name, iceberg_type, metadata_location)` de tabelas e views do namespace, ordenadas."""
    kind = "COALESCE(iceberg_type, 'TABLE')" if has_type else "'TABLE'"
    rows = conn.execute(
        f"SELECT table_name, {kind}, COALESCE(metadata_location, '') FROM iceberg_tables "
        "WHERE catalog_name = ? AND table_namespace = ? ORDER BY table_name",
        (ICEBERG_CATALOG, namespace),
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def all_metadata_locations(conn: sqlite3.Connection) -> list[str]:
    """`metadata_location` de todas as tabelas/views restantes (para checar se uma pasta ainda é usada)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT metadata_location FROM iceberg_tables WHERE catalog_name = ? AND metadata_location IS NOT NULL",
            (ICEBERG_CATALOG,),
        )
    ]


def drop_namespace_rows(conn: sqlite3.Connection, namespace: str) -> None:
    """Remove tabelas/views e as propriedades do namespace (o que `dropTable` e `dropNamespace` fazem no SQL)."""
    conn.execute("DELETE FROM iceberg_tables WHERE catalog_name = ? AND table_namespace = ?", (ICEBERG_CATALOG, namespace))
    conn.execute(
        "DELETE FROM iceberg_namespace_properties WHERE catalog_name = ? AND namespace = ?", (ICEBERG_CATALOG, namespace)
    )


def gc_enabled(metadata_location: str) -> bool | None:
    """`gc.enabled` do metadata atual (padrão true); `None` se o metadata não pôde ser lido."""
    try:
        props = _read_metadata(metadata_location).get("properties")
    except IcebergMetadataError:
        return None
    if not isinstance(props, dict):
        return True
    return str(props.get("gc.enabled", "true")).strip().lower() != "false"


def error_entry(code: str) -> dict[str, Any]:
    """Nó do catálogo `iceberg` quando a leitura degrada."""
    return {"name": ICEBERG_CATALOG, "databases": [], "error": code}


def _read_metadata(location: str) -> dict[str, Any]:
    path = local_path(location)
    if path is None:
        raise IcebergMetadataError("metadata is not on the local disk")
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_METADATA_BYTES + 1)
        if raw[:2] == b"\x1f\x8b":
            raw = zlib.decompressobj(wbits=31).decompress(raw, MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise IcebergMetadataError("metadata too large")
        meta = json.loads(raw)
    except (OSError, ValueError, zlib.error, EOFError) as exc:
        raise IcebergMetadataError(type(exc).__name__) from exc
    if not isinstance(meta, dict):
        raise IcebergMetadataError("unexpected metadata layout")
    return meta


def _type_name(spec: Any, depth: int = 0) -> str:
    """Tipo Iceberg como texto (`list<int>`, `struct<a:string>`); profundidade limitada."""
    if isinstance(spec, str):
        return spec
    if not isinstance(spec, dict) or depth >= _MAX_TYPE_DEPTH:
        return "?"
    kind = spec.get("type")
    if kind == "list":
        return f"list<{_type_name(spec.get('element'), depth + 1)}>"
    if kind == "map":
        return f"map<{_type_name(spec.get('key'), depth + 1)},{_type_name(spec.get('value'), depth + 1)}>"
    if kind == "struct":
        inner = ",".join(f"{f.get('name')}:{_type_name(f.get('type'), depth + 1)}" for f in spec.get("fields", []))
        return f"struct<{inner}>"
    return str(kind or "?")


def _current_schema(meta: dict[str, Any]) -> dict[str, Any]:
    schemas = meta.get("schemas")
    if isinstance(schemas, list) and schemas:
        wanted = meta.get("current-schema-id")
        for schema in schemas:
            if isinstance(schema, dict) and schema.get("schema-id") == wanted:
                return schema
        raise IcebergMetadataError("current schema not found")
    schema = meta.get("schema")  # metadata v1 antigo
    if isinstance(schema, dict):
        return schema
    raise IcebergMetadataError("schema not found")


def _partition_source_ids(meta: dict[str, Any]) -> set[Any]:
    specs = meta.get("partition-specs")
    fields: Any = meta.get("partition-spec")  # metadata v1 antigo
    if isinstance(specs, list):
        default = meta.get("default-spec-id")
        fields = next((s.get("fields") for s in specs if isinstance(s, dict) and s.get("spec-id") == default), [])
    if not isinstance(fields, list):
        return set()
    return {f.get("source-id") for f in fields if isinstance(f, dict)}


def _columns_from_metadata(meta: dict[str, Any]) -> list[dict[str, Any]]:
    schema = _current_schema(meta)
    partitions = _partition_source_ids(meta)
    try:
        return [
            {
                "name": str(f["name"]),
                "data_type": _type_name(f.get("type")),
                "nullable": not f.get("required", False),
                "is_partition": f.get("id") in partitions,
                "is_bucket": False,
                "description": f.get("doc"),
            }
            for f in schema["fields"]
        ]
    except (KeyError, TypeError, AttributeError) as exc:
        raise IcebergMetadataError("unexpected schema layout") from exc


def read_columns(conn: sqlite3.Connection, database: str, table: str) -> list[dict[str, Any]] | None:
    """Colunas de uma tabela Iceberg pelo `metadata.json` atual; `None` se a tabela não existir.

    Levanta `UnsupportedIcebergSchema` ou `IcebergMetadataError`.
    """
    has_type = _check_schema(conn)
    row = conn.execute(
        "SELECT metadata_location FROM iceberg_tables "
        f"WHERE catalog_name = ? AND table_namespace = ? AND table_name = ? {_type_filter(has_type)}",
        (ICEBERG_CATALOG, database, table),
    ).fetchone()
    if row is None:
        return None
    if not row[0]:
        raise IcebergMetadataError("table has no metadata location")
    return _columns_from_metadata(_read_metadata(row[0]))
