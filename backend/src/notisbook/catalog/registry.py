"""Leitura e escrita de schemas do registro `nb_*` (Delta/Parquet/Hudi do `spark_catalog`) sem SparkSession.

As tabelas continuam escritas pelo módulo oculto do kernel; o backend só cria/remove schemas inteiros
(`create_namespace`/`drop_namespace`). A conexão e a transação (`BEGIN IMMEDIATE`) pertencem ao chamador.
Toda escrita sobe `nb_meta.generation`, que é o que faz as sessões abertas reconciliarem.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

SPARK_CATALOG = "spark_catalog"
# Nó só de exibição: as tabelas Hudi vivem no `spark_catalog` (`nb_tables.format = 'hudi'`).
HUDI_CATALOG = "hudi"
DEFAULT_DATABASE = "default"
# Teto da varredura: tabelas por database e no total. Estourar o teto marca `"truncated": true`.
MAX_TABLES = 500
MAX_TOTAL_TABLES = 2000


def _bump_generation(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE nb_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'generation'")


def namespace_exists(conn: sqlite3.Connection, namespace: str) -> bool:
    """`default` sempre existe; os demais, por linha em `nb_namespaces` ou `nb_tables`. Sem distinção de caixa."""
    key = namespace.lower()
    if key == DEFAULT_DATABASE:
        return True
    row = conn.execute(
        "SELECT 1 FROM nb_namespaces WHERE catalog_name = ? AND lower(namespace) = ? "
        "UNION SELECT 1 FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ? LIMIT 1",
        (SPARK_CATALOG, key, SPARK_CATALOG, key),
    ).fetchone()
    return row is not None


def create_namespace(conn: sqlite3.Connection, namespace: str, display_catalog: str = SPARK_CATALOG) -> bool:
    """Registra o schema em minúsculas (como o SessionCatalog); `False` se já existe. Dentro de transação.

    `display_catalog` (`spark_catalog` ou `hudi`) é o nó onde o schema vazio aparece.
    """
    key = namespace.lower()
    if namespace_exists(conn, key):
        return False
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Sem `location`: o hook cria a pasta (`CREATE DATABASE IF NOT EXISTS`) ao hidratar a sessão.
    conn.execute(
        "INSERT INTO nb_namespaces (catalog_name, namespace, location, created_at, display_catalog) VALUES (?, ?, NULL, ?, ?)",
        (SPARK_CATALOG, key, stamp, display_catalog),
    )
    _bump_generation(conn)
    return True


def namespace_tables(conn: sqlite3.Connection, namespace: str) -> list[tuple[str, str, str]]:
    """`(table_name, location, table_type)` das tabelas do schema, ordenadas."""
    rows = conn.execute(
        "SELECT table_name, location, table_type FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ? "
        "ORDER BY table_name",
        (SPARK_CATALOG, namespace.lower()),
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def namespace_hudi_count(conn: sqlite3.Connection, namespace: str) -> int:
    """Quantas tabelas do schema são Hudi (o nó `spark_catalog` não as lista, mas a exclusão do schema as remove)."""
    row = conn.execute(
        "SELECT COUNT(*) FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ? AND format = 'hudi'",
        (SPARK_CATALOG, namespace.lower()),
    ).fetchone()
    return int(row[0])


def all_table_locations(conn: sqlite3.Connection) -> list[str]:
    """Locations de todas as tabelas do registro (para checar se uma pasta ainda é usada)."""
    return [r[0] for r in conn.execute("SELECT location FROM nb_tables WHERE catalog_name = ?", (SPARK_CATALOG,))]


def drop_namespace(conn: sqlite3.Connection, namespace: str) -> None:
    """Remove as linhas de tabelas e do schema (cascade) e sobe a generation. Dentro de transação."""
    key = namespace.lower()
    conn.execute("DELETE FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ?", (SPARK_CATALOG, key))
    conn.execute("DELETE FROM nb_namespaces WHERE catalog_name = ? AND lower(namespace) = ?", (SPARK_CATALOG, key))
    _bump_generation(conn)


def local_path(location: str | None) -> Path | None:
    """Caminho local de uma URI `file:` ou caminho absoluto; `None` para outros esquemas (s3a, hdfs...)."""
    if not location:
        return None
    if location.startswith("file:"):
        return Path(unquote(urlparse(location).path))
    if "://" in location:
        return None
    path = Path(location)
    return path if path.is_absolute() else None


def is_available(location: str | None) -> bool | None:
    """`True`/`False` pelo stat do caminho local; `None` quando o local não é um caminho do disco."""
    path = local_path(location)
    if path is None:
        return None
    try:
        return path.exists()
    except OSError:
        return False


def _table_node(namespace: str, name: str, fmt: str, table_type: str, location: str, description: str | None) -> dict[str, Any]:
    return {
        "name": name,
        "namespace": [namespace],
        "format": fmt,
        "table_type": table_type,
        "is_temporary": False,
        "location": location,
        "available": is_available(location),
        "description": description,
    }


def _display_names(conn: sqlite3.Connection, hudi: bool) -> set[str]:
    """Schemas exibidos no nó: só-Hudi no `hudi`, sem Hudi no `spark_catalog`, mistos nos dois, vazios pela origem."""
    counts: dict[str, tuple[int, int]] = {
        r[0]: (int(r[1]), int(r[2]))
        for r in conn.execute(
            "SELECT namespace, SUM(format = 'hudi'), SUM(format != 'hudi') FROM nb_tables WHERE catalog_name = ? GROUP BY namespace",
            (SPARK_CATALOG,),
        )
    }
    origins = {
        r[0]: r[1]
        for r in conn.execute("SELECT namespace, display_catalog FROM nb_namespaces WHERE catalog_name = ?", (SPARK_CATALOG,))
    }
    node = HUDI_CATALOG if hudi else SPARK_CATALOG
    names = set()
    for ns in {DEFAULT_DATABASE, *counts, *origins}:
        n_hudi, n_other = counts.get(ns, (0, 0))
        if (n_hudi if hudi else n_other) > 0 or (n_hudi + n_other == 0 and origins.get(ns, SPARK_CATALOG) == node):
            names.add(ns)
    return names


def list_databases(conn: sqlite3.Connection, max_total: int, hudi: bool = False) -> tuple[list[dict[str, Any]], int]:
    """Databases do nó e o total de tabelas listadas: `spark_catalog` (sem as Hudi) ou, com `hudi`, só as Hudi.

    `max_total` é o que resta do teto global; databases após o teto voltam vazios e `truncated`.
    Cada schema é um só namespace do `spark_catalog`; a regra de exibição está em `_display_names`.
    """
    fmt_filter = "format = 'hudi'" if hudi else "format != 'hudi'"
    names = _display_names(conn, hudi)
    ordered = sorted(names, key=lambda n: (n != DEFAULT_DATABASE, n))
    used = 0
    databases: list[dict[str, Any]] = []
    for db in ordered:
        if used >= max_total:
            databases.append({"name": db, "tables": [], "truncated": True})
            continue
        limit = min(MAX_TABLES, max_total - used)
        rows = conn.execute(
            "SELECT table_name, format, table_type, location, description FROM nb_tables "
            f"WHERE catalog_name = ? AND namespace = ? AND {fmt_filter} ORDER BY table_name LIMIT ?",
            (SPARK_CATALOG, db, limit + 1),
        ).fetchall()
        entry: dict[str, Any] = {"name": db, "tables": [_table_node(db, *r) for r in rows[:limit]]}
        if len(rows) > limit:
            entry["truncated"] = True
        used += len(entry["tables"])
        databases.append(entry)
    return databases, used


def _decode_columns(raw: str, partitions: set[str]) -> list[dict[str, Any]]:
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("columns_json is not a list")
    return [
        {
            "name": str(c["name"]),
            "data_type": str(c.get("data_type", "")),
            "nullable": bool(c.get("nullable", True)),
            "is_partition": bool(c.get("is_partition")) or str(c["name"]) in partitions,
            "is_bucket": False,
            "description": c.get("description"),
        }
        for c in items
    ]


def read_columns(conn: sqlite3.Connection, database: str, table: str, hudi_only: bool = False) -> list[dict[str, Any]] | None:
    """Colunas de uma tabela do registro (só Hudi com `hudi_only`); `None` se não existir. Nomes sem distinção de caixa."""
    row = conn.execute(
        "SELECT columns_json, partition_cols FROM nb_tables "
        "WHERE catalog_name = ? AND namespace = ? COLLATE NOCASE AND table_name = ? COLLATE NOCASE "
        "AND (? = 0 OR format = 'hudi')",
        (SPARK_CATALOG, database, table, int(hudi_only)),
    ).fetchone()
    if row is None:
        return None
    try:
        partitions = {str(p) for p in json.loads(row[1])}
        return _decode_columns(row[0], partitions)
    except (ValueError, KeyError, TypeError):
        # Registro com JSON ilegível: a tabela existe, só não há colunas para mostrar.
        return []
