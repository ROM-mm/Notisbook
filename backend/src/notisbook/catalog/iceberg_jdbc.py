"""Leitura e escrita do catálogo `iceberg` (JdbcCatalog do Iceberg) direto do SQLite e dos `metadata.json`, sem Spark.

Camada de isolamento sobre o formato INTERNO do JdbcCatalog (tabelas `iceberg_*` e metadata v1/v2):
ele não é API pública. A escrita (`create_namespace`/`drop_namespace_rows`) reproduz o SQL do JdbcCatalog 1.10.1
(`createNamespace` grava `exists=true`; `dropNamespace`/`dropTable` fazem DELETE). Trocar a versão do Iceberg
na MATRIX de bundles exige rever a leitura E a escrita. A transação (`BEGIN IMMEDIATE`) pertence ao chamador.
Formato inesperado degrada só o catálogo `iceberg` (`error`), nunca o resto do painel.
"""

import json
import os
import sqlite3
import zlib
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..fs_safety import is_within
from ..notislake import locations, objectstore
from ..notislake.settings_store import ConfigInvalid
from .registry import MAX_TABLES, all_table_locations, is_available, local_path

ICEBERG_CATALOG = "iceberg"
ERR_UNSUPPORTED = "unsupported_iceberg_catalog_schema"
ERR_UNREADABLE = "iceberg_catalog_unreadable"
# Teto do `metadata.json` (já descomprimido): evita carregar um arquivo gigante ou uma bomba gzip.
MAX_METADATA_BYTES = 16 * 1024 * 1024
_MAX_TYPE_DEPTH = 8
# Entrega a conexão do bucket sob demanda: tabelas locais nunca resolvem (nem exigem) o MinIO.
StoreOpener = Callable[[], objectstore.Connection]

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


class MetadataStoreUnavailable(IcebergMetadataError):
    """O bucket do metadata está fora do ar ou sem configuração válida (distinto de metadata ilegível)."""


class MetadataOutsideRoot(IcebergMetadataError):
    """O `metadata_location` aponta para fora das raízes permitidas (ou não é um caminho local)."""


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


def is_managed_s3a(metadata_location: str | None, namespace: str, table: str) -> bool:
    """O metadata está em `s3a://notisbook-managed/<ns>/<t>` (`<warehouse>/<ns>/<t>` do JdbcCatalog, grafia exata).

    Só sintático, sem consultar o bucket.
    """
    prefix = table_prefix(metadata_location)
    try:
        return prefix is not None and prefix == locations.managed_location(namespace, table)
    except locations.InvalidLocation:
        return False


def _table_type(metadata_location: str, namespace: str, table: str) -> str:
    """MANAGED só em `s3a://notisbook-managed/<ns>/<t>`; qualquer outro caminho (inclusive local) é EXTERNAL; informativo."""
    return "MANAGED" if is_managed_s3a(metadata_location, namespace, table) else "EXTERNAL"


def table_prefix(location: str | None) -> str | None:
    """Prefixo `s3a://<bucket>/...` da tabela (pai de `metadata/`); `None` se não for uma location s3 válida."""
    try:
        parsed = locations.parse_location(location or "")
    except locations.InvalidLocation:
        return None
    segments = parsed.segments[:-1]
    if segments and segments[-1] == "metadata":
        segments = segments[:-1]
    return locations.Location(parsed.bucket, segments).uri if segments else None


def _shown_location(metadata_location: str) -> str | None:
    folder = _table_dir(metadata_location)
    if folder is not None:
        return folder.as_uri()
    return table_prefix(metadata_location) or metadata_location or None


def _node(row: tuple[Any, ...]) -> dict[str, Any]:
    namespace, name, metadata_location = row[0], row[1], row[2] or ""
    shown = _shown_location(metadata_location)
    return {
        "name": name,
        "namespace": namespace.split("."),
        "format": "iceberg",
        "table_type": _table_type(metadata_location, namespace, name),
        "is_temporary": False,
        "location": shown,
        # Fora do disco local (s3a) a disponibilidade é desconhecida: não se sonda o bucket na listagem.
        "available": is_available(metadata_location),
        "description": None,
    }


def all_namespaces(conn: sqlite3.Connection) -> list[str]:
    """Todos os namespaces do `iceberg` (propriedades e tabelas), ordenados."""
    return sorted(name for (name,) in _namespace_names(conn))


def _namespace_names(conn: sqlite3.Connection) -> sqlite3.Cursor:
    """Namespaces do `iceberg`: união de `iceberg_namespace_properties` e `iceberg_tables` (1 coluna, sem ordem)."""
    return conn.execute(
        "SELECT namespace FROM iceberg_namespace_properties WHERE catalog_name = ? "
        "UNION SELECT table_namespace FROM iceberg_tables WHERE catalog_name = ?",
        (ICEBERG_CATALOG, ICEBERG_CATALOG),
    )


def list_databases(conn: sqlite3.Connection, max_total: int) -> tuple[list[dict[str, Any]], int]:
    """Databases (namespaces) do `iceberg` e o total de tabelas listadas.

    Namespaces = união de `iceberg_namespace_properties` e `iceberg_tables`: o Iceberg só grava propriedades
    quando o namespace é criado explicitamente. Levanta `UnsupportedIcebergSchema`.
    """
    has_type = _check_schema(conn)
    names = {r[0] for r in _namespace_names(conn)}
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
        entry: dict[str, Any] = {"name": db, "tables": [_node(r) for r in rows[:limit]]}
        if len(rows) > limit:
            entry["truncated"] = True
        used += len(entry["tables"])
        databases.append(entry)
    return databases, used


def catalog_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Contagens exatas do `iceberg` (sem `MAX_TABLES`/`MAX_TOTAL_TABLES`): tabelas e views por namespace.

    Namespaces pela mesma união de `list_databases`; views só existem quando `iceberg_type` existe.
    Levanta `UnsupportedIcebergSchema` (e propaga `sqlite3.Error`) para o chamador degradar o status.
    """
    has_type = _check_schema(conn)
    names = {r[0] for r in _namespace_names(conn)}
    is_table = _TABLE_FILTER if has_type else "1"
    is_view = "iceberg_type = 'VIEW'" if has_type else "0"
    tables: dict[str, int] = {}
    views: dict[str, int] = {}
    for namespace, n_tables, n_views in conn.execute(
        f"SELECT table_namespace, SUM({is_table}), SUM({is_view}) FROM iceberg_tables WHERE catalog_name = ? GROUP BY table_namespace",
        (ICEBERG_CATALOG,),
    ):
        tables[namespace] = int(n_tables or 0)
        views[namespace] = int(n_views or 0)
    ordered = sorted(names)
    total_tables = sum(tables.get(ns, 0) for ns in names)
    return {
        "namespaces": [{"name": ns, "tables": tables.get(ns, 0), "views": views.get(ns, 0)} for ns in ordered],
        "tables": total_tables,
        "views": sum(views.get(ns, 0) for ns in names),
        "formats": {"iceberg": total_tables} if total_tables else {},
    }


def check_schema(conn: sqlite3.Connection) -> bool:
    """Valida o formato antes de escrever; devolve se `iceberg_type` existe. Levanta `UnsupportedIcebergSchema`."""
    return _check_schema(conn)


def table_folder(metadata_location: str | None) -> Path | None:
    """Pasta da tabela a partir do `metadata_location` (None se não for um caminho local, como em `s3a`)."""
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


def known_table_locations(conn: sqlite3.Connection) -> list[str]:
    """Pasta de toda tabela conhecida: registro `nb_*` (locations) e Iceberg (pai de `metadata/`); entrada da regra de sobreposição."""
    prefixes = (table_prefix(loc) for loc in all_metadata_locations(conn))
    return [*all_table_locations(conn), *(p for p in prefixes if p is not None)]


def drop_namespace_rows(conn: sqlite3.Connection, namespace: str) -> None:
    """Remove tabelas/views e as propriedades do namespace (o que `dropTable` e `dropNamespace` fazem no SQL)."""
    conn.execute("DELETE FROM iceberg_tables WHERE catalog_name = ? AND table_namespace = ?", (ICEBERG_CATALOG, namespace))
    conn.execute(
        "DELETE FROM iceberg_namespace_properties WHERE catalog_name = ? AND namespace = ?", (ICEBERG_CATALOG, namespace)
    )


def gc_enabled(metadata_location: str, open_store: StoreOpener | None = None) -> bool | None:
    """`gc.enabled` do metadata atual (padrão true); `None` se o metadata não pôde ser lido."""
    try:
        props = read_metadata(metadata_location, open_store).get("properties")
    except IcebergMetadataError:
        return None
    if not isinstance(props, dict):
        return True
    return str(props.get("gc.enabled", "true")).strip().lower() != "false"


def error_entry(code: str) -> dict[str, Any]:
    """Nó do catálogo `iceberg` quando a leitura degrada."""
    return {"name": ICEBERG_CATALOG, "databases": [], "error": code}


def _parse_metadata(raw: bytes) -> dict[str, Any]:
    """Interpreta o conteúdo do `metadata.json` (gzip é detectado pelo cabeçalho), respeitando o teto descomprimido."""
    try:
        if raw[:2] == b"\x1f\x8b":
            raw = zlib.decompressobj(wbits=31).decompress(raw, MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise IcebergMetadataError("metadata too large")
        meta = json.loads(raw)
    except (ValueError, zlib.error, EOFError) as exc:
        raise IcebergMetadataError(type(exc).__name__) from exc
    if not isinstance(meta, dict):
        raise IcebergMetadataError("unexpected metadata layout")
    return meta


def _read_remote(location: str, open_store: StoreOpener | None) -> bytes:
    """Bytes do metadata em `s3a://<bucket>/...`, lidos com teto, com a conexão do object store do app."""
    try:
        parsed = locations.parse_location(location)
    except locations.InvalidLocation as exc:
        raise IcebergMetadataError("metadata is not on the local disk") from exc
    if open_store is None:
        raise IcebergMetadataError("object store not provided")
    try:
        return objectstore.get_bounded(open_store(), parsed.key, max_bytes=MAX_METADATA_BYTES, bucket=parsed.bucket)
    except objectstore.ObjectStoreError as exc:
        if exc.code in (objectstore.TIMEOUT, objectstore.UNREACHABLE):
            raise MetadataStoreUnavailable("object store unavailable") from None
        raise IcebergMetadataError(exc.code) from None
    except (objectstore.Unavailable, ConfigInvalid):
        raise MetadataStoreUnavailable("object store unavailable") from None


def read_metadata(location: str, open_store: StoreOpener | None = None) -> dict[str, Any]:
    """`metadata.json` local ou em `s3a://<bucket>/...` (lido com teto). Levanta `IcebergMetadataError` ou `MetadataStoreUnavailable`."""
    path = local_path(location)
    if path is None:
        return _parse_metadata(_read_remote(location, open_store))
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_METADATA_BYTES + 1)
    except OSError as exc:
        raise IcebergMetadataError(type(exc).__name__) from exc
    return _parse_metadata(raw)


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


_HISTORY_LIMIT = 50
_STATS_KEYS = (("total_records", "total-records"), ("total_files_size", "total-files-size"), ("total_data_files", "total-data-files"))


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _snapshots(meta: dict[str, Any]) -> list[dict[str, Any]]:
    raw = meta.get("snapshots")
    return [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []


def _iso_from_ms(value: Any) -> str | None:
    ms = _int_or_none(value)
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _id_text(value: Any) -> str | None:
    """Id de snapshot como texto: são `long` de 64 bits e perderiam precisão como número no JSON do navegador."""
    number = _int_or_none(value)
    return None if number is None else str(number)


def _history(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Últimos snapshots por `timestamp-ms`, do mais recente para o mais antigo."""
    ordered = sorted(snapshots, key=lambda s: _int_or_none(s.get("timestamp-ms")) or 0, reverse=True)
    entries = []
    for snap in ordered[:_HISTORY_LIMIT]:
        summary = snap.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        entries.append(
            {
                "id": _id_text(snap.get("snapshot-id")),
                "timestamp_ms": _int_or_none(snap.get("timestamp-ms")),
                "operation": str(summary["operation"]) if summary.get("operation") is not None else None,
                "parent_id": _id_text(snap.get("parent-snapshot-id")),
                "summary": {str(k): str(v) for k, v in summary.items() if k != "operation"},
            }
        )
    return entries


def _current_snapshot(meta: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any] | None:
    wanted = _int_or_none(meta.get("current-snapshot-id"))
    if wanted is None or wanted < 0:
        return None
    return next((s for s in snapshots if _int_or_none(s.get("snapshot-id")) == wanted), None)


def _table_info_from_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Campos do envelope que vêm do `metadata.json`. Levanta `IcebergMetadataError` se o schema não for legível."""
    columns = _columns_from_metadata(meta)
    raw_props = meta.get("properties")
    properties = {str(k): str(v) for k, v in raw_props.items()} if isinstance(raw_props, dict) else {}
    snapshots = _snapshots(meta)
    current = _current_snapshot(meta, snapshots)
    summary = current.get("summary") if current else None
    summary = summary if isinstance(summary, dict) else {}
    current_id = _id_text(current.get("snapshot-id")) if current else None
    return {
        "description": properties.get("comment"),
        "updated_at": _iso_from_ms(meta.get("last-updated-ms")),
        "partition_columns": [c["name"] for c in columns if c["is_partition"]],
        "columns": columns,
        "version": {"kind": "iceberg_snapshot", "value": current_id},
        "history": _history(snapshots),
        "properties": properties,
        "stats": {key: _int_or_none(summary.get(source)) for key, source in _STATS_KEYS},
    }


def read_table_info(
    conn: sqlite3.Connection, database: str, table: str, open_store: StoreOpener | None = None
) -> dict[str, Any] | None:
    """Metadados de uma tabela Iceberg (envelope de `registry.read_table_info`); `None` se a tabela não existir.

    Falha no `metadata.json` não propaga: os campos do SQLite ficam e `metadata_error` vira `unavailable`
    ou `store_unavailable`. Levanta `UnsupportedIcebergSchema`.
    """
    has_type = _check_schema(conn)
    row = conn.execute(
        "SELECT metadata_location FROM iceberg_tables "
        f"WHERE catalog_name = ? AND table_namespace = ? AND table_name = ? {_type_filter(has_type)}",
        (ICEBERG_CATALOG, database, table),
    ).fetchone()
    if row is None:
        return None
    metadata_location = row[0] or ""
    info: dict[str, Any] = {
        "catalog": ICEBERG_CATALOG,
        "database": database,
        "table": table,
        "format": "iceberg",
        "table_type": _table_type(metadata_location, database, table),
        # A MANAGED (`<warehouse>/<ns>/<t>`) entra na fila de exclusão no DROP; a externa só sai do registro.
        "drop_behavior": "deletes_files" if is_managed_s3a(metadata_location, database, table) else "registry_only",
        "location": _shown_location(metadata_location),
        "available": is_available(metadata_location),
        "description": None,
        "created_at": None,
        "updated_at": None,
        "partition_columns": [],
        "columns": [],
        "version": None,
        "history": None,
        "properties": None,
        "stats": None,
        "metadata_error": None,
    }
    try:
        if not metadata_location:
            raise IcebergMetadataError("table has no metadata location")
        info.update(_table_info_from_metadata(read_metadata(metadata_location, open_store)))
    except MetadataStoreUnavailable:
        info["metadata_error"] = "store_unavailable"
    except IcebergMetadataError:
        info["metadata_error"] = "unavailable"
    return info


def location_within_root(location: str, root: str) -> bool:
    """True se `location` é um caminho local cujo realpath fica estritamente dentro de `root`."""
    path = local_path(location)
    if path is None:
        return False
    real, real_root = Path(os.path.realpath(path)), Path(os.path.realpath(root))
    return real != real_root and is_within(real, real_root)


def location_within_roots(location: str, roots: Sequence[str]) -> bool:
    """True se `location` fica estritamente dentro de alguma das `roots` (realpath)."""
    return any(location_within_root(location, root) for root in roots)


def read_metadata_within(location: str, roots: Sequence[str]) -> dict[str, Any]:
    """`metadata.json` em `location`, aberto só se o realpath estiver dentro de alguma das `roots`.

    Levanta `MetadataOutsideRoot` (fora das raízes / não local) ou `IcebergMetadataError` (ilegível).
    """
    path = local_path(location)
    if path is None or not location_within_roots(location, roots):
        raise MetadataOutsideRoot("metadata outside the allowed roots")
    return read_metadata(str(Path(os.path.realpath(path))))


def list_child_namespaces(conn: sqlite3.Connection, parent: str | None) -> list[str]:
    """Namespaces do próximo nível abaixo de `parent` (ou do topo), como o `JdbcCatalog.listNamespaces`."""
    rows = _namespace_names(conn)
    prefix = f"{parent}." if parent else ""
    children = set()
    for (name,) in rows:
        if name.startswith(prefix) and len(name) > len(prefix):
            children.add(prefix + name[len(prefix) :].split(".", 1)[0])
    return sorted(children)


def namespace_properties(conn: sqlite3.Connection, namespace: str) -> dict[str, str]:
    """Propriedades do namespace, sem o marcador interno `exists`."""
    rows = conn.execute(
        "SELECT property_key, property_value FROM iceberg_namespace_properties "
        "WHERE catalog_name = ? AND namespace = ? AND property_key IS NOT NULL AND property_key <> 'exists'",
        (ICEBERG_CATALOG, namespace),
    )
    return {k: v for k, v in rows if v is not None}


def list_table_names(conn: sqlite3.Connection, namespace: str, has_type: bool) -> list[str]:
    """Nomes das tabelas (sem views) do namespace, ordenados."""
    return [name for name, kind, _ in namespace_entries(conn, namespace, has_type) if kind == "TABLE"]


def table_metadata_location(conn: sqlite3.Connection, namespace: str, table: str, has_type: bool) -> str | None:
    """`metadata_location` da tabela; `None` se ela não existe; `""` se existe sem metadata."""
    row = conn.execute(
        "SELECT COALESCE(metadata_location, '') FROM iceberg_tables "
        f"WHERE catalog_name = ? AND table_namespace = ? AND table_name = ? {_type_filter(has_type)}",
        (ICEBERG_CATALOG, namespace, table),
    ).fetchone()
    return None if row is None else str(row[0])


def insert_table(conn: sqlite3.Connection, namespace: str, table: str, metadata_location: str, has_type: bool) -> bool:
    """INSERT do `JdbcCatalog.createTable` (V1); `False` se já existe tabela ou view com o nome, ignorando a caixa.

    Dentro de transação: a checagem sem caixa evita que `T` e `t` dividam a pasta (APFS).
    """
    if table_row_exists(conn, namespace, table, ignore_case=True):
        return False
    columns = "catalog_name, table_namespace, table_name, metadata_location, previous_metadata_location"
    values = "?, ?, ?, ?, NULL"
    if has_type:
        columns += ", iceberg_type"
        values += ", 'TABLE'"
    try:
        conn.execute(
            f"INSERT INTO iceberg_tables ({columns}) VALUES ({values})",
            (ICEBERG_CATALOG, namespace, table, metadata_location),
        )
    except sqlite3.IntegrityError:
        return False
    return True


def swap_metadata_location(
    conn: sqlite3.Connection, namespace: str, table: str, expected: str, new: str, has_type: bool
) -> bool:
    """CAS do commit, com o mesmo predicado do `JdbcTableOperations`; `False` se a localização atual mudou."""
    cursor = conn.execute(
        "UPDATE iceberg_tables SET metadata_location = ?, previous_metadata_location = ? "
        f"WHERE catalog_name = ? AND table_namespace = ? AND table_name = ? AND metadata_location = ? {_type_filter(has_type)}",
        (new, expected, ICEBERG_CATALOG, namespace, table, expected),
    )
    return cursor.rowcount == 1


def delete_table_row(conn: sqlite3.Connection, namespace: str, table: str, has_type: bool) -> bool:
    """`DELETE` do `JdbcCatalog.dropTable`; `False` se a tabela não existe."""
    cursor = conn.execute(
        f"DELETE FROM iceberg_tables WHERE catalog_name = ? AND table_namespace = ? AND table_name = ? {_type_filter(has_type)}",
        (ICEBERG_CATALOG, namespace, table),
    )
    return cursor.rowcount == 1


def table_row_exists(conn: sqlite3.Connection, namespace: str, table: str, *, ignore_case: bool = False) -> bool:
    """Existe tabela OU view com esse nome (a chave primária é a mesma); `ignore_case` compara sem caixa."""
    match = "lower(table_name) = lower(?)" if ignore_case else "table_name = ?"
    row = conn.execute(
        f"SELECT 1 FROM iceberg_tables WHERE catalog_name = ? AND table_namespace = ? AND {match}",
        (ICEBERG_CATALOG, namespace, table),
    ).fetchone()
    return row is not None


def rename_table_row(
    conn: sqlite3.Connection, source: tuple[str, str], target: tuple[str, str], has_type: bool
) -> bool:
    """`UPDATE` do `JdbcCatalog.renameTable`; `False` se a origem não existe. O destino deve ser checado antes."""
    cursor = conn.execute(
        "UPDATE iceberg_tables SET table_namespace = ?, table_name = ? "
        f"WHERE catalog_name = ? AND table_namespace = ? AND table_name = ? {_type_filter(has_type)}",
        (target[0], target[1], ICEBERG_CATALOG, source[0], source[1]),
    )
    return cursor.rowcount == 1


def set_namespace_properties(conn: sqlite3.Connection, namespace: str, properties: dict[str, str]) -> None:
    for key, value in properties.items():
        conn.execute(
            "INSERT OR REPLACE INTO iceberg_namespace_properties (catalog_name, namespace, property_key, property_value) "
            "VALUES (?, ?, ?, ?)",
            (ICEBERG_CATALOG, namespace, key, value),
        )


def remove_namespace_property(conn: sqlite3.Connection, namespace: str, key: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM iceberg_namespace_properties WHERE catalog_name = ? AND namespace = ? AND property_key = ?",
        (ICEBERG_CATALOG, namespace, key),
    )
    return cursor.rowcount > 0
