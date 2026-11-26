"""Pré-visualizar e remover uma tabela do `spark_catalog` só do registro `nb_tables`, sem SparkSession.

Serve às linhas órfãs (sem pasta, que o hook não hidrata nem o DROP alcança). Remove a linha e não mexe em
`nb_namespaces`. A MANAGED na própria pasta, se ninguém mais a usa, tem a pasta enfileirada em `nb_pending_deletions`
na mesma transação; o backend nunca apaga arquivos (o kernel apaga, rechecando o uso). Sem `reserve_idle`: as
sessões abertas convergem pela `generation`. Ordem: `BEGIN IMMEDIATE` -> relê -> confere o etag -> DELETE -> COMMIT.
Funções síncronas (rodam em thread); erros de regra levantam `TableError`.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..notislake import locations
from . import registry
from .store import catalog_db_path, connect
from .store import immediate as _immediate

NAME_MAX = 256

_STATUS = {
    "invalid_catalog": 400,
    "invalid_name": 400,
    "table_not_found": 404,
    "catalog_changed": 409,
}


class TableError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.status = _STATUS[code]


# Linha armazenada: namespace, table_name, location, table_type, updated_at.
_Row = tuple[str, str, str, str, str]


def validate(catalog: str, database: str, table: str) -> None:
    """Só `spark_catalog`; nomes não vazios, até `NAME_MAX` e sem caracteres de controle (são parâmetros ligados)."""
    if catalog != registry.SPARK_CATALOG:
        raise TableError("invalid_catalog")
    for name in (database, table):
        if not name or len(name) > NAME_MAX or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            raise TableError("invalid_name")


def _etag(row: _Row) -> str:
    return hashlib.sha256(json.dumps(list(row)).encode()).hexdigest()[:16]


def _find(conn: sqlite3.Connection, database: str, table: str) -> _Row | None:
    """Linha pela chave sem distinção de caixa (como `read_table_info`); a de caixa exata vem primeiro."""
    row = conn.execute(
        "SELECT namespace, table_name, location, table_type, updated_at FROM nb_tables "
        "WHERE catalog_name = ? AND namespace = ? COLLATE NOCASE AND table_name = ? COLLATE NOCASE "
        "ORDER BY (namespace = ? AND table_name = ?) DESC LIMIT 1",
        (registry.SPARK_CATALOG, database, table, database, table),
    ).fetchone()
    return None if row is None else (row[0], row[1], row[2], row[3], row[4])


def _is_own_managed(row: _Row) -> bool:
    return row[3] == "MANAGED" and locations.is_own_managed(row[0], row[1], row[2])


def _queues_files(conn: sqlite3.Connection, row: _Row) -> bool:
    """A remoção enfileira a pasta: MANAGED própria, fila disponível e nenhuma outra tabela usa a pasta."""
    return (
        _is_own_managed(row)
        and registry.has_pending_table(conn)
        and not registry.folder_in_use(conn, row[2], skip=(row[0], row[1]))
    )


def preview_table(home: Path, catalog: str, database: str, table: str) -> dict[str, Any]:
    """Efeito da remoção e o `etag` que o DELETE exige. Levanta `TableError`, `sqlite3.Error`."""
    validate(catalog, database, table)
    if not catalog_db_path(home).exists():
        raise TableError("table_not_found")
    conn = connect(home)
    try:
        conn.execute("PRAGMA query_only=ON")
        row = _find(conn, database, table)
        queues = row is not None and _queues_files(conn, row)
    finally:
        conn.close()
    if row is None:
        raise TableError("table_not_found")
    return {
        "catalog": registry.SPARK_CATALOG,
        "database": row[0],
        "table": row[1],
        "table_type": row[3],
        "location": row[2],
        "remove_effect": "queues_files" if queues else "registry_only",
        "can_remove": True,
        "reason": None,
        "etag": _etag(row),
    }


def remove_table(home: Path, catalog: str, database: str, table: str, etag: str) -> dict[str, Any]:
    """Remove a linha da tabela se o etag ainda vale. Levanta `TableError`, `sqlite3.Error`."""
    validate(catalog, database, table)
    if not catalog_db_path(home).exists():
        raise TableError("table_not_found")
    conn = connect(home)
    try:
        with _immediate(conn):
            row = _find(conn, database, table)
            if row is None:
                raise TableError("table_not_found")
            if _etag(row) != etag:
                raise TableError("catalog_changed")
            queues = _queues_files(conn, row)
            if not registry.delete_table_row(conn, row[0], row[1], row[2]):
                raise TableError("catalog_changed")
            if queues:
                stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                registry.enqueue_deletion(conn, registry.SPARK_CATALOG, (row[0], row[1]), row[2], stamp)
            generation = registry.read_generation(conn)
    finally:
        conn.close()
    return {
        "removed": {"catalog": registry.SPARK_CATALOG, "database": row[0], "table": row[1]},
        "files_deleted": [],
        "files_queued": [row[2]] if queues else [],
        "generation": generation,
    }
