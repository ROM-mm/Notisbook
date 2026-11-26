"""Criar, pré-visualizar e excluir schemas (spark_catalog, iceberg e glue) sem SparkSession.

Ordem da exclusão: `BEGIN IMMEDIATE` -> valida e confere o etag -> DELETE das linhas -> COMMIT. Não existe
warehouse local: as tabelas MANAGED vivem no bucket reservado (`s3a`) e o backend nunca apaga arquivos, então a
cascata só remove linhas e enfileira as pastas MANAGED em `nb_pending_deletions` (`files_queued`; o kernel as apaga).
`files_kept` traz o que fica, com o motivo do DROP de tabela: `keeps_files_shared` (MANAGED própria cuja pasta outra
tabela usa), `keeps_files_outside_managed` (MANAGED s3 fora da própria pasta), `no_deletion_queue` (própria e livre, mas o
`catalog.db` não tem a fila) e `outside_warehouse` (location local).
No `glue` a cascata remove database, tabelas e partições; só a pasta própria livre (MANAGED ou Iceberg) é enfileirada, e
o etag cobre as linhas e o efeito. A criação grava o `LocationUri` `s3://notisbook-managed/<nome>`, como o seed.
As linhas do próprio schema saem juntas e não seguram a pasta. `folder_kept` é sempre falso: não há pasta de schema a remover. O `default` do `spark_catalog` e do `glue` não é excluível (`cannot_drop_default`).
Funções síncronas (rodam em thread); erros de regra levantam `SchemaError`.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..notislake import locations
from . import glue_repo, iceberg_jdbc, registry
from .names import NAME_RE
from .store import catalog_db_path, connect, ensure_catalog_db
from .store import immediate as _immediate

RESERVED_SPARK = {"global_temp"}
RESERVED_GLUE = {"global_temp"}

_STATUS = {
    "invalid_catalog": 400,
    "invalid_name": 400,
    "reserved_name": 400,
    "schema_not_found": 404,
    "schema_exists": 409,
    "catalog_changed": 409,
    "cannot_drop_default": 409,
    "namespace_case_collision": 409,
    "has_child_namespaces": 409,
    "unsupported_iceberg_catalog_schema": 409,
}


class SchemaError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.status = _STATUS[code]


def validate(catalog: str, name: str) -> None:
    if catalog not in (registry.SPARK_CATALOG, iceberg_jdbc.ICEBERG_CATALOG, glue_repo.GLUE_CATALOG):
        raise SchemaError("invalid_catalog")
    if NAME_RE.fullmatch(name) is None:
        raise SchemaError("invalid_name")


def _etag(items: list[list[str]]) -> str:
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:16]


def _spark_etag(rows: list[tuple[str, str, str]], queued: list[str]) -> str:
    """Etag das linhas do schema e das tabelas que a exclusão enfileiraria: mudar o uso da pasta invalida a prévia."""
    return _etag([list(r) for r in rows] + [["queued", *sorted(queued)]])


def _iceberg_etag(entries: list[tuple[str, str, str]], queued: list[str]) -> str:
    """Etag das entradas do namespace e das tabelas que a exclusão enfileiraria (o efeito entra, como no spark)."""
    items = []
    for name, kind, location in entries:
        folder = iceberg_jdbc.table_folder(location)
        items.append([name, kind, str(folder) if folder is not None else location])
    return _etag([*items, ["queued", *sorted(queued)]])


def _open_read(home: Path) -> sqlite3.Connection | None:
    if not catalog_db_path(home).exists():
        return None
    conn = connect(home)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _open_existing_for_delete(home: Path) -> sqlite3.Connection:
    """Conexão de escrita para excluir; sem `catalog.db` não há schema, e o arquivo não é criado."""
    if not catalog_db_path(home).exists():
        raise SchemaError("schema_not_found")
    return connect(home)


def _open_write(home: Path) -> sqlite3.Connection:
    if not catalog_db_path(home).exists():
        ensure_catalog_db(home)
    return connect(home)


def create_schema(home: Path, catalog: str, name: str) -> dict[str, str]:
    """Cria o schema; o `spark_catalog` grava em minúsculas. Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, name)
    if catalog == glue_repo.GLUE_CATALOG:
        return _create_glue(home, name)
    if catalog == registry.SPARK_CATALOG:
        if name.lower() in RESERVED_SPARK:
            raise SchemaError("reserved_name")
        name = name.lower()
    conn = _open_write(home)
    try:
        if catalog == iceberg_jdbc.ICEBERG_CATALOG:
            try:
                iceberg_jdbc.check_schema(conn)
            except iceberg_jdbc.UnsupportedIcebergSchema as exc:
                raise SchemaError("unsupported_iceberg_catalog_schema") from exc
        with _immediate(conn):
            if catalog == registry.SPARK_CATALOG:
                created = registry.create_namespace(conn, name)
            else:
                if not iceberg_jdbc.namespace_exists(conn, name) and iceberg_jdbc.namespace_exists(conn, name, ignore_case=True):
                    raise SchemaError("namespace_case_collision")  # a pasta no bucket não distingue a caixa
                created = iceberg_jdbc.create_namespace(conn, name)
            if not created:
                raise SchemaError("schema_exists")
    finally:
        conn.close()
    return {"catalog": catalog, "name": name}


def _create_glue(home: Path, name: str) -> dict[str, str]:
    """Cria o database `glue` em minúsculas com `LocationUri` `s3://notisbook-managed/<nome>`, como o seed.

    Sem o LocationUri o hook recusa tabela gerenciada (`schema_location_missing`). Não sobe a `generation`.
    """
    key = name.lower()
    if key in RESERVED_GLUE:
        raise SchemaError("reserved_name")
    try:
        with glue_repo.writer(home) as conn:
            glue_repo.create_database(conn, {"Name": key, "LocationUri": locations.schema_location(key, "s3")})
    except glue_repo.GlueAlreadyExists as exc:
        raise SchemaError("schema_exists") from exc
    return {"catalog": glue_repo.GLUE_CATALOG, "name": key}


def _own_keys(schema: str, rows: list[tuple[str, str, str]]) -> set[tuple[str, str]]:
    """Chaves das tabelas do schema que saem na mesma operação; não seguram a pasta umas das outras."""
    return {(schema.lower(), table) for table, _, _ in rows}


def _keep_reason(schema: str, table: str, location: str, used: list[str], has_queue: bool) -> str | None:
    """`None` se a pasta da MANAGED vai para a fila; senão o motivo, com os rótulos de `registry._drop_behavior`.

    `used` vem de `registry.used_folders` (uma consulta por operação); `outside_warehouse` é só location local.
    """
    if not locations.is_own_managed(schema, table, location):
        return "outside_warehouse" if registry.local_path(location) is not None else "keeps_files_outside_managed"
    folder = registry.folder_key(location)
    if any(registry.folder_overlaps(folder, u) for u in used):
        return "keeps_files_shared"
    return None if has_queue else "no_deletion_queue"  # `catalog.db` sem a migração da fila


def _managed_plan(conn: sqlite3.Connection, schema: str, rows: list[tuple[str, str, str]]) -> list[tuple[str, str, str | None]]:
    """`(tabela, location, motivo | None)` de cada MANAGED do schema; `None` = enfileirada. Prévia e DELETE usam esta."""
    has_queue = registry.has_pending_table(conn)
    used = registry.used_folders(conn, _own_keys(schema, rows))
    return [
        (table, location, _keep_reason(schema, table, location, used, has_queue))
        for table, location, kind in rows
        if kind == "MANAGED"
    ]


def _preview_spark(home: Path, schema: str, conn: sqlite3.Connection | None) -> dict[str, Any]:
    key = schema.lower()
    if conn is None:
        if key != registry.DEFAULT_DATABASE:
            raise SchemaError("schema_not_found")
        rows: list[tuple[str, str, str]] = []
    else:
        if not registry.namespace_exists(conn, key):
            raise SchemaError("schema_not_found")
        rows = registry.namespace_tables(conn, key)
    plan = _managed_plan(conn, key, rows) if conn is not None else []
    managed = len(plan)
    queued_tables = [table for table, _, reason in plan if reason is None]
    queued = len(queued_tables)
    is_default = key == registry.DEFAULT_DATABASE
    # `tables` conta todos os formatos. O backend não apaga arquivos: `managed` (apagadas por ele) é sempre 0, a pasta
    # MANAGED própria e livre vai para a fila (`managed_queued`) e o resto das MANAGED fica (`managed_kept`: location
    # local, fora da própria pasta, pasta em uso por outra tabela ou sem fila); `external` são as não MANAGED.
    return {
        "tables": len(rows),
        "views": 0,
        "managed": 0,
        "managed_queued": queued,
        "managed_kept": managed - queued,
        "external": len(rows) - managed,
        "can_delete": not is_default,
        "reason": "cannot_drop_default" if is_default else None,
        "etag": _spark_etag(rows, queued_tables),
    }


def _iceberg_plan(conn: sqlite3.Connection, schema: str, entries: list[tuple[str, str, str]]) -> list[tuple[str, str, str | None]]:
    """`(tabela, pasta, motivo | None)` de cada tabela Iceberg na pasta gerenciada própria; `None` = enfileirada.

    Mesma regra de pasta em uso do spark e do glue; as entradas do próprio namespace (views inclusive) não a seguram.
    Prévia e DELETE usam esta.
    """
    has_queue = registry.has_pending_table(conn)
    used = registry.used_folders(conn, skip_tables=[(iceberg_jdbc.ICEBERG_CATALOG, schema, name) for name, _, _ in entries])
    plan: list[tuple[str, str, str | None]] = []
    for name, kind, location in entries:
        prefix = iceberg_jdbc.table_prefix(location)
        if kind == "VIEW" or prefix is None or not iceberg_jdbc.is_managed_s3a(location, schema, name):
            continue
        folder = registry.folder_key(prefix)
        if any(registry.folder_overlaps(folder, u) for u in used):
            reason = "keeps_files_shared"
        else:
            reason = None if has_queue else "no_deletion_queue"
        plan.append((name, prefix, reason))
    return plan


def _preview_iceberg(schema: str, conn: sqlite3.Connection | None) -> dict[str, Any]:
    if conn is None:
        raise SchemaError("schema_not_found")
    try:
        has_type = iceberg_jdbc.check_schema(conn)
    except iceberg_jdbc.UnsupportedIcebergSchema as exc:
        raise SchemaError("unsupported_iceberg_catalog_schema") from exc
    if not iceberg_jdbc.namespace_exists(conn, schema):
        raise SchemaError("schema_not_found")
    entries = iceberg_jdbc.namespace_entries(conn, schema, has_type)
    tables = [e for e in entries if e[1] != "VIEW"]
    plan = _iceberg_plan(conn, schema, entries)
    queued_tables = [name for name, _, reason in plan if reason is None]
    children = iceberg_jdbc.has_child_namespaces(conn, schema)
    return {
        "tables": len(tables),
        "views": len(entries) - len(tables),
        "managed": 0,  # o backend não apaga arquivos do bucket
        "managed_queued": len(queued_tables),
        "managed_kept": len(plan) - len(queued_tables),
        "external": len(tables) - len(plan),
        "can_delete": not children,
        "reason": "has_child_namespaces" if children else None,
        "etag": _iceberg_etag(entries, queued_tables),
    }


_GlueRow = tuple[str, str, str | None, int, float, bool]


def _glue_etag(schema: str, database: tuple[str, str | None, float] | None, rows: list[_GlueRow], queued: list[str]) -> str:
    """Etag do database, das tabelas (identidade e versão) e das que a exclusão enfileiraria."""
    head = ["database", schema, *(str(v) for v in database)] if database else ["database", schema]
    items = [[name, kind, location or "", str(version), str(created), str(iceberg)] for name, kind, location, version, created, iceberg in rows]
    return _etag([head, *items, ["queued", *sorted(queued)]])


def _glue_plan(conn: sqlite3.Connection, schema: str, rows: list[_GlueRow]) -> list[tuple[str, str, str | None]]:
    """`(tabela, location, motivo | None)` de cada tabela com pasta a enfileirar ou a manter; `None` = enfileirada.

    Entram a MANAGED_TABLE e o Iceberg na pasta própria (`glue_repo.owns_folder`); os outros formatos são só do catálogo.
    As tabelas do próprio schema saem juntas e não seguram a pasta umas das outras. Prévia e DELETE usam esta.
    """
    has_queue = registry.has_pending_table(conn)
    used = registry.used_folders(conn, skip_tables=[(glue_repo.GLUE_CATALOG, schema, name) for name, *_ in rows])
    plan = []
    for name, table_type, location, _version, _created, iceberg in rows:
        managed = table_type == glue_repo.TABLE_TYPE_MANAGED
        own = glue_repo.owns_folder(schema, name, location, managed=managed, iceberg=iceberg)
        if location and (own or managed):
            plan.append((name, location, _keep_reason(schema, name, location, used, has_queue)))
    return plan


def _preview_glue(schema: str, conn: sqlite3.Connection | None) -> dict[str, Any]:
    key = schema.lower()
    is_default = key == registry.DEFAULT_DATABASE
    database = glue_repo.find_database(conn, key) if conn is not None else None
    if database is None and not is_default:
        raise SchemaError("schema_not_found")
    rows = glue_repo.database_tables(conn, key) if conn is not None else []
    plan = _glue_plan(conn, key, rows) if conn is not None else []
    queued_tables = [table for table, _, reason in plan if reason is None]
    return {
        "tables": len(rows),
        "views": 0,
        "managed": 0,  # o backend não apaga arquivos do bucket
        "managed_queued": len(queued_tables),
        "managed_kept": len(plan) - len(queued_tables),
        "external": len(rows) - len(plan),
        "can_delete": not is_default,
        "reason": "cannot_drop_default" if is_default else None,
        "etag": _glue_etag(key, database, rows, queued_tables),
    }


def _delete_glue(home: Path, schema: str, etag: str) -> dict[str, Any]:
    key = schema.lower()
    if key == registry.DEFAULT_DATABASE:
        raise SchemaError("cannot_drop_default")
    conn = _open_existing_for_delete(home)
    try:
        with _immediate(conn):
            database = glue_repo.find_database(conn, key)
            if database is None:
                raise SchemaError("schema_not_found")
            rows = glue_repo.database_tables(conn, key)
            plan = _glue_plan(conn, key, rows)
            if _glue_etag(key, database, rows, [t for t, _, reason in plan if reason is None]) != etag:
                raise SchemaError("catalog_changed")
            glue_repo.drop_database_rows(conn, key)
            queued = _queue_managed(
                conn, glue_repo.GLUE_CATALOG, key, [(t, loc) for t, loc, reason in plan if reason is None])
            kept = [{"table": table, "reason": reason} for table, _, reason in plan if reason is not None]
    finally:
        conn.close()

    return {
        "dropped_tables": len(rows),
        "dropped_views": 0,
        "files_deleted": [],
        "files_queued": queued,
        "files_kept": kept,
        "folder_kept": False,
    }


def preview_schema(home: Path, catalog: str, schema: str) -> dict[str, Any]:
    """Contagens e etag do que a exclusão removeria. Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, schema)
    conn = _open_read(home)
    try:
        if catalog == registry.SPARK_CATALOG:
            return _preview_spark(home, schema, conn)
        if catalog == glue_repo.GLUE_CATALOG:
            return _preview_glue(schema, conn)
        if catalog == iceberg_jdbc.ICEBERG_CATALOG:
            return _preview_iceberg(schema, conn)
        raise SchemaError("invalid_catalog")
    finally:
        if conn is not None:
            conn.close()


def _delete_spark(home: Path, schema: str, etag: str) -> dict[str, Any]:
    key = schema.lower()
    if key == registry.DEFAULT_DATABASE:
        raise SchemaError("cannot_drop_default")
    conn = _open_existing_for_delete(home)
    try:
        with _immediate(conn):
            if not registry.namespace_exists(conn, key):
                raise SchemaError("schema_not_found")
            rows = registry.namespace_tables(conn, key)
            plan = _managed_plan(conn, key, rows)
            if _spark_etag(rows, [t for t, _, reason in plan if reason is None]) != etag:
                raise SchemaError("catalog_changed")
            registry.drop_namespace(conn, key)
            queued = _queue_managed(
                conn, registry.SPARK_CATALOG, key, [(t, loc) for t, loc, reason in plan if reason is None])
            kept = [{"table": table, "reason": reason} for table, _, reason in plan if reason is not None]
    finally:
        conn.close()

    return {
        "dropped_tables": len(rows),
        "dropped_views": 0,
        "files_deleted": [],
        "files_queued": queued,
        "files_kept": kept,
        "folder_kept": False,
    }


def _queue_managed(conn: sqlite3.Connection, catalog: str, schema: str, tables: list[tuple[str, str]]) -> list[str]:
    """Enfileira (na transação da exclusão) a pasta de cada tabela MANAGED do bucket reservado; devolve os nomes.

    Quem decide o que entra é o chamador (`_managed_plan` no spark_catalog). O backend não apaga arquivos: o kernel
    consome a fila, depois de rechecar que nenhuma tabela usa a pasta.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    queued = []
    for table, location in tables:
        if locations.managed_table(location) and registry.enqueue_deletion(conn, catalog, (schema, table), location, stamp):
            queued.append(table)
    return queued


def _delete_iceberg(home: Path, schema: str, etag: str) -> dict[str, Any]:
    conn = _open_existing_for_delete(home)
    try:
        try:
            has_type = iceberg_jdbc.check_schema(conn)
        except iceberg_jdbc.UnsupportedIcebergSchema as exc:
            raise SchemaError("unsupported_iceberg_catalog_schema") from exc
        with _immediate(conn):
            if not iceberg_jdbc.namespace_exists(conn, schema):
                raise SchemaError("schema_not_found")
            if iceberg_jdbc.has_child_namespaces(conn, schema):
                raise SchemaError("has_child_namespaces")
            entries = iceberg_jdbc.namespace_entries(conn, schema, has_type)
            plan = _iceberg_plan(conn, schema, entries)
            if _iceberg_etag(entries, [name for name, _, reason in plan if reason is None]) != etag:
                raise SchemaError("catalog_changed")
            iceberg_jdbc.drop_namespace_rows(conn, schema)
            tables = [e for e in entries if e[1] != "VIEW"]
            queued = _queue_managed(
                conn, iceberg_jdbc.ICEBERG_CATALOG, schema, [(name, prefix) for name, prefix, reason in plan if reason is None])
            kept = [{"table": name, "reason": reason} for name, _, reason in plan if reason is not None]
    finally:
        conn.close()

    return {
        "dropped_tables": len(tables),
        "dropped_views": len(entries) - len(tables),
        "files_deleted": [],
        "files_queued": queued,
        "files_kept": kept,
        "folder_kept": False,
    }


def delete_schema(home: Path, catalog: str, schema: str, etag: str) -> dict[str, Any]:
    """Exclui o schema em cascata (ordem no docstring do módulo). Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, schema)
    if catalog == registry.SPARK_CATALOG:
        return _delete_spark(home, schema, etag)
    if catalog == glue_repo.GLUE_CATALOG:
        return _delete_glue(home, schema, etag)
    if catalog == iceberg_jdbc.ICEBERG_CATALOG:
        return _delete_iceberg(home, schema, etag)
    raise SchemaError("invalid_catalog")
