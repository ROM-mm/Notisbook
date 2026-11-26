"""Pré-visualizar e remover uma tabela do `spark_catalog`, `glue` ou `iceberg` só do catálogo, sem SparkSession.

Serve às linhas órfãs (sem pasta, que o hook não hidrata nem o DROP alcança) e à remoção pelo painel. Remove a linha
(no `glue`, também as partições) e não mexe em schema. A tabela na própria pasta gerenciada, se ninguém mais a usa, tem
a pasta enfileirada em `nb_pending_deletions` (rótulo do catálogo) na mesma transação; o backend nunca apaga arquivos
(o kernel apaga, rechecando o uso). Cada catálogo tem um adaptador (`_ADAPTERS`) que acha a linha e a remove.
Só o `spark_catalog` sobe a `generation` (reconcilia as sessões abertas); `glue`/`iceberg` exigem kernels ociosos na rota.
Ordem: `BEGIN IMMEDIATE` -> relê -> confere o etag -> DELETE -> COMMIT. Funções síncronas (rodam em thread); erros de
regra levantam `TableError`.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..notislake import locations
from . import glue_repo, iceberg_jdbc, registry
from .store import catalog_db_path, connect
from .store import immediate as _immediate

NAME_MAX = 256

_STATUS = {
    "invalid_catalog": 400,
    "invalid_name": 400,
    "table_not_found": 404,
    "catalog_changed": 409,
    iceberg_jdbc.ERR_UNSUPPORTED: 409,
}


class TableError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.status = _STATUS[code]


@dataclass(frozen=True)
class _Entry:
    """Linha de uma tabela em qualquer catálogo.

    `version` é o que mais identifica a linha no etag (nos catálogos que não são o `spark_catalog`, começa pelo rótulo
    do catálogo); `folder` é a pasta gerenciada própria (candidata à fila) ou `None`.
    """

    catalog: str
    database: str
    table: str
    location: str
    table_type: str
    version: tuple[Any, ...]
    folder: str | None


@dataclass(frozen=True)
class _Adapter:
    find: Callable[[sqlite3.Connection, str, str], _Entry | None]
    delete: Callable[[sqlite3.Connection, _Entry], bool]


def _find_spark(conn: sqlite3.Connection, database: str, table: str) -> _Entry | None:
    """Linha pela chave sem distinção de caixa (como `read_table_info`); a de caixa exata vem primeiro."""
    row = conn.execute(
        "SELECT namespace, table_name, location, table_type, updated_at FROM nb_tables "
        "WHERE catalog_name = ? AND namespace = ? COLLATE NOCASE AND table_name = ? COLLATE NOCASE "
        "ORDER BY (namespace = ? AND table_name = ?) DESC LIMIT 1",
        (registry.SPARK_CATALOG, database, table, database, table),
    ).fetchone()
    if row is None:
        return None
    namespace, name, location, table_type, updated = row
    own = table_type == "MANAGED" and locations.is_own_managed(namespace, name, location)
    return _Entry(registry.SPARK_CATALOG, namespace, name, location, table_type, (updated,), location if own else None)


def _delete_spark(conn: sqlite3.Connection, entry: _Entry) -> bool:
    return registry.delete_table_row(conn, entry.database, entry.table, entry.location)


def _find_glue(conn: sqlite3.Connection, database: str, table: str) -> _Entry | None:
    """Tabela `glue`; o Iceberg do `glue_catalog` é EXTERNAL_TABLE, mas a pasta própria dele também é enfileirada."""
    row = glue_repo.find_table_row(conn, database, table)
    if row is None:
        return None
    namespace, name, glue_type, location, version_id, created, iceberg = row
    managed = glue_type == glue_repo.TABLE_TYPE_MANAGED
    own = glue_repo.owns_folder(namespace, name, location, managed=managed, iceberg=iceberg)
    return _Entry(
        glue_repo.GLUE_CATALOG, namespace, name, location or "", "MANAGED" if managed else "EXTERNAL",
        (glue_repo.GLUE_CATALOG, version_id, created), location if own else None,
    )


def _delete_glue(conn: sqlite3.Connection, entry: _Entry) -> bool:
    return glue_repo.delete_table_row(conn, entry.database, entry.table)


def _find_iceberg(conn: sqlite3.Connection, database: str, table: str) -> _Entry | None:
    """Tabela `iceberg` (sem views) pela chave exata; o `metadata_location` entra no etag (todo commit o troca)."""
    try:
        has_type = iceberg_jdbc.check_schema(conn)
        metadata = iceberg_jdbc.table_metadata_location(conn, database, table, has_type)
    except iceberg_jdbc.UnsupportedIcebergSchema:
        raise TableError(iceberg_jdbc.ERR_UNSUPPORTED) from None
    if metadata is None:
        return None
    prefix = iceberg_jdbc.table_prefix(metadata)
    own = iceberg_jdbc.is_managed_s3a(metadata, database, table)
    return _Entry(
        iceberg_jdbc.ICEBERG_CATALOG, database, table, prefix or metadata, "MANAGED" if own else "EXTERNAL",
        (iceberg_jdbc.ICEBERG_CATALOG, metadata),
        prefix if own else None,
    )


def _delete_iceberg(conn: sqlite3.Connection, entry: _Entry) -> bool:
    try:
        return iceberg_jdbc.delete_table_row(conn, entry.database, entry.table, iceberg_jdbc.check_schema(conn))
    except iceberg_jdbc.UnsupportedIcebergSchema:
        raise TableError(iceberg_jdbc.ERR_UNSUPPORTED) from None


_ADAPTERS: dict[str, _Adapter] = {
    registry.SPARK_CATALOG: _Adapter(_find_spark, _delete_spark),
    iceberg_jdbc.ICEBERG_CATALOG: _Adapter(_find_iceberg, _delete_iceberg),
    glue_repo.GLUE_CATALOG: _Adapter(_find_glue, _delete_glue),
}


def validate(catalog: str, database: str, table: str) -> None:
    """Catálogo com adaptador; nomes não vazios, até `NAME_MAX` e sem caracteres de controle (são parâmetros ligados)."""
    if catalog not in _ADAPTERS:
        raise TableError("invalid_catalog")
    for name in (database, table):
        if not name or len(name) > NAME_MAX or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            raise TableError("invalid_name")


def _etag(entry: _Entry, queues: bool) -> str:
    """Hash da linha e do efeito da remoção: mudança de `queues_files`/`registry_only` invalida a prévia."""
    row = [entry.database, entry.table, entry.location, entry.table_type, *entry.version]
    return hashlib.sha256(json.dumps([*row, queues]).encode()).hexdigest()[:16]


def _queues_files(conn: sqlite3.Connection, entry: _Entry) -> bool:
    """A remoção enfileira a pasta: própria gerenciada, fila disponível e nenhuma outra tabela usa a pasta."""
    return (
        entry.folder is not None
        and registry.has_pending_table(conn)
        and not registry.folder_in_use(conn, entry.folder, skip_tables=[(entry.catalog, entry.database, entry.table)])
    )


def preview_table(home: Path, catalog: str, database: str, table: str) -> dict[str, Any]:
    """Efeito da remoção e o `etag` que o DELETE exige. Levanta `TableError`, `sqlite3.Error`."""
    validate(catalog, database, table)
    if not catalog_db_path(home).exists():
        raise TableError("table_not_found")
    conn = connect(home)
    try:
        conn.execute("PRAGMA query_only=ON")
        entry = _ADAPTERS[catalog].find(conn, database, table)
        queues = entry is not None and _queues_files(conn, entry)
    finally:
        conn.close()
    if entry is None:
        raise TableError("table_not_found")
    return {
        "catalog": entry.catalog,
        "database": entry.database,
        "table": entry.table,
        "table_type": entry.table_type,
        "location": entry.location,
        "remove_effect": "queues_files" if queues else "registry_only",
        "can_remove": True,
        "reason": None,
        "etag": _etag(entry, queues),
    }


def remove_table(home: Path, catalog: str, database: str, table: str, etag: str) -> dict[str, Any]:
    """Remove a linha da tabela se o etag ainda vale. Levanta `TableError`, `sqlite3.Error`."""
    validate(catalog, database, table)
    if not catalog_db_path(home).exists():
        raise TableError("table_not_found")
    adapter = _ADAPTERS[catalog]
    conn = connect(home)
    try:
        with _immediate(conn):
            entry = adapter.find(conn, database, table)
            if entry is None:
                raise TableError("table_not_found")
            queues = _queues_files(conn, entry)
            if _etag(entry, queues) != etag:
                raise TableError("catalog_changed")
            if not adapter.delete(conn, entry):
                raise TableError("catalog_changed")
            if queues:
                stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                registry.enqueue_deletion(conn, entry.catalog, (entry.database, entry.table), entry.folder or "", stamp)
            generation = registry.read_generation(conn)
    finally:
        conn.close()
    return {
        "removed": {"catalog": entry.catalog, "database": entry.database, "table": entry.table},
        "files_deleted": [],
        "files_queued": [entry.folder] if queues else [],
        "generation": generation,
    }
