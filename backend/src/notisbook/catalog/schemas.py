"""Criar, pré-visualizar e excluir schemas (spark_catalog e iceberg) sem SparkSession.

Ordem da exclusão: `BEGIN IMMEDIATE` -> valida e confere o etag -> DELETE das linhas -> COMMIT. Não existe
warehouse local: as tabelas MANAGED vivem no bucket (`s3a`) e o backend nunca apaga por prefixo, então a
cascata só remove linhas e devolve os arquivos mantidos em `files_kept` (`s3a_kept`; `outside_warehouse` para
uma linha MANAGED legada com location local). `folder_kept` é sempre falso: não há pasta de schema a remover.
As 3 camadas do notislake (`locations.LAYERS`) existem nos dois catálogos e não são excluíveis (`cannot_drop_layer`).
Funções síncronas (rodam em thread); erros de regra levantam `SchemaError`.
"""

import hashlib
import json
import re
import sqlite3
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
    "cannot_drop_layer": 409,
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
    kept = sum(1 for r in rows if r[2] == "MANAGED" and locations.managed_table(r[1]))
    is_default = key == registry.DEFAULT_DATABASE
    is_layer = locations.layer_of_schema(key) is not None
    # `tables` conta todos os formatos. O backend não apaga arquivos: `managed` (apagadas) é sempre 0 e as pastas
    # MANAGED s3a ficam no bucket (`managed_kept`); `external` segue sendo as linhas que não são MANAGED.
    return {
        "tables": len(rows),
        "views": 0,
        "managed": 0,
        "managed_kept": kept,
        "external": len(rows) - managed,
        "can_delete": not (is_default or is_layer),
        "reason": "cannot_drop_default" if is_default else "cannot_drop_layer" if is_layer else None,
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
    kept = sum(1 for n, _, loc in tables if iceberg_jdbc.is_managed_s3a(loc, schema, n))
    children = iceberg_jdbc.has_child_namespaces(conn, schema)
    is_layer = schema in locations.LAYERS  # no Iceberg a caixa conta: `Bronze` legado não é camada
    return {
        "tables": len(tables),
        "views": len(entries) - len(tables),
        "managed": 0,  # o backend não apaga arquivos do bucket
        "managed_kept": kept,
        "external": len(tables) - kept,
        "can_delete": not (children or is_layer),
        "reason": "cannot_drop_layer" if is_layer else "has_child_namespaces" if children else None,
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
    if locations.layer_of_schema(key) is not None:
        raise SchemaError("cannot_drop_layer")
    conn = _open_existing_for_delete(home)
    try:
        with _immediate(conn):
            if not registry.namespace_exists(conn, key):
                raise SchemaError("schema_not_found")
            rows = registry.namespace_tables(conn, key)
            if _spark_etag(rows) != etag:
                raise SchemaError("catalog_changed")
            registry.drop_namespace(conn, key)
    finally:
        conn.close()

    kept: list[dict[str, str]] = []
    for table, location, table_type in rows:
        if table_type == "MANAGED":
            reason = "s3a_kept" if locations.managed_table(location) else "outside_warehouse"
            kept.append({"table": table, "reason": reason})
    return {
        "dropped_tables": len(rows),
        "dropped_views": 0,
        "files_deleted": [],
        "files_kept": kept,
        "folder_kept": False,
    }


def _delete_iceberg(home: Path, schema: str, etag: str) -> dict[str, Any]:
    if schema in locations.LAYERS:
        raise SchemaError("cannot_drop_layer")
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
    finally:
        conn.close()

    tables = [e for e in entries if e[1] != "VIEW"]
    kept = [
        {"table": name, "reason": "s3a_kept"}  # o backend não apaga por prefixo no bucket
        for name, _, loc in tables
        if iceberg_jdbc.is_managed_s3a(loc, schema, name)
    ]
    return {
        "dropped_tables": len(tables),
        "dropped_views": len(entries) - len(tables),
        "files_deleted": [],
        "files_kept": kept,
        "folder_kept": False,
    }


def delete_schema(home: Path, catalog: str, schema: str, etag: str) -> dict[str, Any]:
    """Exclui o schema em cascata (ordem no docstring do módulo). Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, schema)
    if catalog == registry.SPARK_CATALOG:
        return _delete_spark(home, schema, etag)
    return _delete_iceberg(home, schema, etag)
