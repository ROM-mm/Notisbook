"""Criar, pré-visualizar e excluir schemas (spark_catalog e iceberg) sem SparkSession.

Ordem da exclusão: `BEGIN IMMEDIATE` -> valida e confere o etag -> DELETE das linhas -> COMMIT -> apaga as pastas
MANAGED -> `rmdir` não recursivo da pasta do schema. Nenhum I/O de arquivo com o lock aberto, e o catálogo
nunca aponta para dado já apagado. Falha ao apagar arquivo não é erro: volta em `files_kept`/`folder_kept`.
Funções síncronas (rodam em thread); erros de regra levantam `SchemaError`.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..fs_safety import is_within
from ..spark.bundles import SPARK_WAREHOUSE_SUBDIR, WAREHOUSE_DIR
from . import iceberg_jdbc, registry
from .managed import managed_table_dir
from .store import catalog_db_path, connect, ensure_catalog_db

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
RESERVED_SPARK = {"global_temp"}

_STATUS = {
    "invalid_catalog": 400,
    "read_only_catalog": 400,
    "invalid_name": 400,
    "reserved_name": 400,
    "schema_not_found": 404,
    "schema_exists": 409,
    "catalog_changed": 409,
    "cannot_drop_default": 409,
    "has_child_namespaces": 409,
    "unsupported_iceberg_catalog_schema": 409,
}


class SchemaError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.status = _STATUS[code]


def validate(catalog: str, name: str) -> None:
    if catalog == registry.HUDI_CATALOG:
        raise SchemaError("read_only_catalog")  # nó de exibição: os schemas pertencem ao `spark_catalog`
    if catalog not in (registry.SPARK_CATALOG, iceberg_jdbc.ICEBERG_CATALOG):
        raise SchemaError("invalid_catalog")
    if not NAME_RE.match(name):
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


@contextmanager
def _immediate(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    conn.execute("COMMIT")


def _spark_root(home: Path) -> Path:
    return home / WAREHOUSE_DIR / SPARK_WAREHOUSE_SUBDIR


def _iceberg_root(home: Path) -> Path:
    return home / WAREHOUSE_DIR / "iceberg"


def _iceberg_managed_dir(location: str, warehouse: Path, namespace: str, table: str) -> str | None:
    """Pasta MANAGED de uma tabela Iceberg: realpath == `<warehouse>/<ns>/<t>` (nunca outra pasta do warehouse)."""
    folder = iceberg_jdbc.table_folder(location)
    if folder is None:
        return None
    real, error = managed_table_dir(folder, warehouse / namespace)
    if error or real is None:
        return None
    expected = os.path.join(os.path.realpath(warehouse), namespace, table)
    return real if real == expected else None


def _in_use(real: str, others: list[str]) -> bool:
    """True se alguma outra pasta é igual, está dentro ou contém `real`; sem caixa (APFS), na dúvida mantém."""
    target = Path(real)
    return any(is_within(Path(o), target, fold=True) or is_within(target, Path(o), fold=True) for o in others)


def _remaining_folders(spark_locations: list[str], iceberg_locations: list[str]) -> list[str]:
    """Pastas (realpath) ainda referenciadas por tabelas do registro e do Iceberg."""
    paths: list[Path | None] = [registry.local_path(loc) for loc in spark_locations]
    paths += [iceberg_jdbc.table_folder(loc) for loc in iceberg_locations]
    return [os.path.realpath(p) for p in paths if p is not None]


def _remove_folder(real: str, others: list[str], table: str, deleted: list[str], kept: list[dict[str, str]]) -> None:
    if _in_use(real, others):
        kept.append({"table": table, "reason": "in_use"})
        return
    if not os.path.isdir(real):
        return
    try:
        shutil.rmtree(real)
    except OSError:
        kept.append({"table": table, "reason": "delete_failed"})
        return
    deleted.append(table)


def _rmdir_schema_folder(folder: Path, root: Path) -> bool:
    """`rmdir` não recursivo da pasta do schema; devolve `folder_kept` (existe e ficou)."""
    if not os.path.lexists(folder):
        return False
    if os.path.realpath(folder) != os.path.join(os.path.realpath(root), folder.name):
        return True
    try:
        os.rmdir(folder)
    except OSError:
        return True
    return False


def create_schema(home: Path, catalog: str, name: str) -> dict[str, str]:
    """Cria o schema; `spark_catalog` grava em minúsculas. Levanta `SchemaError`, `sqlite3.Error`."""
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
            module: Any = registry if catalog == registry.SPARK_CATALOG else iceberg_jdbc
            if not module.create_namespace(conn, name):
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
        hudi = 0
    else:
        if not registry.namespace_exists(conn, key):
            raise SchemaError("schema_not_found")
        rows = registry.namespace_tables(conn, key)
        hudi = registry.namespace_hudi_count(conn, key)
    managed = sum(1 for r in rows if r[2] == "MANAGED")
    is_default = key == registry.DEFAULT_DATABASE
    # `tables` exclui as Hudi (o que o nó lista); `managed`/`external` cobrem todas as linhas, pois a exclusão age sobre todas.
    return {
        "tables": len(rows) - hudi,
        "hudi": hudi,
        "views": 0,
        "managed": managed,
        "external": len(rows) - managed,
        "can_delete": not is_default,
        "reason": "cannot_drop_default" if is_default else None,
        "etag": _spark_etag(rows),
    }


def _preview_iceberg(home: Path, schema: str, conn: sqlite3.Connection | None) -> dict[str, Any]:
    if conn is None:
        raise SchemaError("schema_not_found")
    try:
        has_type = iceberg_jdbc.check_schema(conn)
    except iceberg_jdbc.UnsupportedIcebergSchema as exc:
        raise SchemaError("unsupported_iceberg_catalog_schema") from exc
    if not iceberg_jdbc.namespace_exists(conn, schema):
        raise SchemaError("schema_not_found")
    entries = iceberg_jdbc.namespace_entries(conn, schema, has_type)
    warehouse = _iceberg_root(home)
    tables = [e for e in entries if e[1] != "VIEW"]
    managed = sum(1 for n, _, loc in tables if _iceberg_managed_dir(loc, warehouse, schema, n) is not None)
    children = iceberg_jdbc.has_child_namespaces(conn, schema)
    return {
        "tables": len(tables),
        "hudi": 0,
        "views": len(entries) - len(tables),
        "managed": managed,
        "external": len(tables) - managed,
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
        return _preview_iceberg(home, schema, conn)
    finally:
        if conn is not None:
            conn.close()


def _delete_spark(home: Path, schema: str, etag: str) -> dict[str, Any]:
    key = schema.lower()
    if key == registry.DEFAULT_DATABASE:
        raise SchemaError("cannot_drop_default")
    root = _spark_root(home)
    conn = _open_existing_for_delete(home)
    try:
        with _immediate(conn):
            if not registry.namespace_exists(conn, key):
                raise SchemaError("schema_not_found")
            rows = registry.namespace_tables(conn, key)
            if _spark_etag(rows) != etag:
                raise SchemaError("catalog_changed")
            registry.drop_namespace(conn, key)
            spark_left = registry.all_table_locations(conn)
            iceberg_left = iceberg_jdbc.all_metadata_locations(conn)
    finally:
        conn.close()

    others = _remaining_folders(spark_left, iceberg_left)
    deleted: list[str] = []
    kept: list[dict[str, str]] = []
    for table, location, table_type in rows:
        if table_type != "MANAGED":
            continue
        path = registry.local_path(location)
        real, error = managed_table_dir(path, root) if path is not None else (None, "not local")
        expected = os.path.join(os.path.realpath(root), f"{key}.db", table)
        if real is None or error or real != expected:
            kept.append({"table": table, "reason": "outside_warehouse"})
            continue
        _remove_folder(real, others, table, deleted, kept)
    folder_kept = _rmdir_schema_folder(root / f"{key}.db", root)
    return {
        "dropped_tables": len(rows),
        "dropped_views": 0,
        "files_deleted": deleted,
        "files_kept": kept,
        "folder_kept": folder_kept,
    }


def _delete_iceberg(home: Path, schema: str, etag: str) -> dict[str, Any]:
    warehouse = _iceberg_root(home)
    conn = _open_existing_for_delete(home)
    try:
        try:
            has_type = iceberg_jdbc.check_schema(conn)
        except iceberg_jdbc.UnsupportedIcebergSchema as exc:
            raise SchemaError("unsupported_iceberg_catalog_schema") from exc
        # Leitura do metadata.json (gc.enabled) fica fora da transação: sem I/O de arquivo com o lock aberto.
        gc: dict[str, bool | None] = {}
        for name, kind, loc in iceberg_jdbc.namespace_entries(conn, schema, has_type):
            if kind != "VIEW" and _iceberg_managed_dir(loc, warehouse, schema, name) is not None:
                gc[name] = iceberg_jdbc.gc_enabled(loc)
        with _immediate(conn):
            if not iceberg_jdbc.namespace_exists(conn, schema):
                raise SchemaError("schema_not_found")
            if iceberg_jdbc.has_child_namespaces(conn, schema):
                raise SchemaError("has_child_namespaces")
            entries = iceberg_jdbc.namespace_entries(conn, schema, has_type)
            if _iceberg_etag(entries) != etag:
                raise SchemaError("catalog_changed")
            iceberg_jdbc.drop_namespace_rows(conn, schema)
            iceberg_left = iceberg_jdbc.all_metadata_locations(conn)
            spark_left = registry.all_table_locations(conn)
    finally:
        conn.close()

    others = _remaining_folders(spark_left, iceberg_left)
    deleted: list[str] = []
    kept: list[dict[str, str]] = []
    tables = [e for e in entries if e[1] != "VIEW"]
    for name, _, loc in tables:
        real = _iceberg_managed_dir(loc, warehouse, schema, name)
        if real is None:
            continue
        enabled = gc.get(name)
        if enabled is None:
            kept.append({"table": name, "reason": "metadata_unreadable"})
        elif not enabled:
            kept.append({"table": name, "reason": "gc_disabled"})
        else:
            _remove_folder(real, others, name, deleted, kept)
    folder_kept = _rmdir_schema_folder(warehouse / schema, warehouse)
    return {
        "dropped_tables": len(tables),
        "dropped_views": len(entries) - len(tables),
        "files_deleted": deleted,
        "files_kept": kept,
        "folder_kept": folder_kept,
    }


def delete_schema(home: Path, catalog: str, schema: str, etag: str) -> dict[str, Any]:
    """Exclui o schema em cascata (ordem no docstring do módulo). Levanta `SchemaError`, `sqlite3.Error`."""
    validate(catalog, schema)
    if catalog == registry.SPARK_CATALOG:
        return _delete_spark(home, schema, etag)
    return _delete_iceberg(home, schema, etag)
