"""Criar, pré-visualizar e excluir schemas (spark_catalog e iceberg) sem SparkSession.

Ordem da exclusão: `BEGIN IMMEDIATE` -> valida e confere o etag -> DELETE das linhas -> COMMIT. Não existe
warehouse local: as tabelas MANAGED vivem no bucket reservado (`s3a`) e o backend nunca apaga arquivos, então a
cascata só remove linhas e enfileira as pastas MANAGED em `nb_pending_deletions` (`files_queued`; o kernel as apaga).
`files_kept` traz o que fica: uma linha MANAGED legada com location local (`outside_warehouse`). `folder_kept` é sempre
falso: não há pasta de schema a remover. Só o `default` do `spark_catalog` não é excluível (`cannot_drop_default`).
Funções síncronas (rodam em thread); erros de regra levantam `SchemaError`.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..notislake import locations
from . import iceberg_jdbc, registry
from .store import catalog_db_path, connect, ensure_catalog_db
from .store import immediate as _immediate

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
RESERVED_SPARK = {"global_temp"}

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
    if catalog not in (registry.SPARK_CATALOG, iceberg_jdbc.ICEBERG_CATALOG):
        raise SchemaError("invalid_catalog")
    if NAME_RE.fullmatch(name) is None:
        raise SchemaError("invalid_name")


def _etag(items: list[list[str]]) -> str:
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:16]


def _spark_etag(rows: list[tuple[str, str, str]]) -> str:
    return _etag([list(r) for r in rows])


def _iceberg_etag(entries: list[tuple[str, str, str]]) -> str:
    items = []
    for name, kind, location in entries:
        folder = iceberg_jdbc.table_folder(location)
        items.append([name, kind, str(folder) if folder is not None else location])
    return _etag(items)


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
    managed = sum(1 for r in rows if r[2] == "MANAGED")
    queued = sum(1 for r in rows if r[2] == "MANAGED" and locations.managed_table(r[1]))
    is_default = key == registry.DEFAULT_DATABASE
    # `tables` conta todos os formatos. O backend não apaga arquivos: `managed` (apagadas por ele) é sempre 0, as pastas
    # MANAGED do bucket reservado vão para a fila de exclusão (`managed_queued`) e a MANAGED legada local fica
    # (`managed_kept`); `external` segue sendo as linhas que não são MANAGED.
    return {
        "tables": len(rows),
        "views": 0,
        "managed": 0,
        "managed_queued": queued,
        "managed_kept": managed - queued,
        "external": len(rows) - managed,
        "can_delete": not is_default,
        "reason": "cannot_drop_default" if is_default else None,
        "etag": _spark_etag(rows),
    }


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
    queued = sum(1 for n, _, loc in tables if iceberg_jdbc.is_managed_s3a(loc, schema, n))
    children = iceberg_jdbc.has_child_namespaces(conn, schema)
    return {
        "tables": len(tables),
        "views": len(entries) - len(tables),
        "managed": 0,  # o backend não apaga arquivos do bucket
        "managed_queued": queued,
        "managed_kept": 0,
        "external": len(tables) - queued,
        "can_delete": not children,
        "reason": "has_child_namespaces" if children else None,
        "etag": _iceberg_etag(entries),
    }


def preview_schema(home: Path, catalog: str, schema: str) -> dict[str, Any]:
    """Contagens e etag do que a exclusão removeria. Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, schema)
    conn = _open_read(home)
    try:
        if catalog == registry.SPARK_CATALOG:
            return _preview_spark(home, schema, conn)
        return _preview_iceberg(schema, conn)
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
            if _spark_etag(rows) != etag:
                raise SchemaError("catalog_changed")
            registry.drop_namespace(conn, key)
            queued = _queue_managed(conn, registry.SPARK_CATALOG, key, [(t, loc) for t, loc, kind in rows if kind == "MANAGED"])
    finally:
        conn.close()

    kept = [
        {"table": table, "reason": "outside_warehouse"}
        for table, location, table_type in rows
        if table_type == "MANAGED" and table not in queued
    ]
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

    O backend não apaga arquivos: o kernel consome a fila, depois de rechecar que nenhuma tabela usa a pasta.
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
            if _iceberg_etag(entries) != etag:
                raise SchemaError("catalog_changed")
            iceberg_jdbc.drop_namespace_rows(conn, schema)
            tables = [e for e in entries if e[1] != "VIEW"]
            managed = [
                (name, prefix)
                for name, _, loc in tables
                if iceberg_jdbc.is_managed_s3a(loc, schema, name) and (prefix := iceberg_jdbc.table_prefix(loc))
            ]
            queued = _queue_managed(conn, iceberg_jdbc.ICEBERG_CATALOG, schema, managed)
    finally:
        conn.close()

    return {
        "dropped_tables": len(tables),
        "dropped_views": len(entries) - len(tables),
        "files_deleted": [],
        "files_queued": queued,
        "files_kept": [],
        "folder_kept": False,
    }


def delete_schema(home: Path, catalog: str, schema: str, etag: str) -> dict[str, Any]:
    """Exclui o schema em cascata (ordem no docstring do módulo). Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, schema)
    if catalog == registry.SPARK_CATALOG:
        return _delete_spark(home, schema, etag)
    return _delete_iceberg(home, schema, etag)
