"""Criação e conexão do `catalog.db`: registro `nb_*` do Notisbook e tabelas do Iceberg JdbcCatalog.

O backend é o único que cria/altera tabelas. O DDL `iceberg_*` replica o que o `JdbcCatalog` do
Iceberg 1.10.1 (schema V1) cria, mas com `IF NOT EXISTS`, para que kernels concorrentes não disputem a criação.
"""

import sqlite3
from pathlib import Path

CATALOG_DB = "catalog.db"

# Espelha o `JdbcUtil` do Iceberg 1.10.1: tabela base + `ALTER ... ADD COLUMN iceberg_type` (V1 com views).
# Revisar ao trocar a versão do Iceberg na MATRIX de bundles.
_ICEBERG_DDL = (
    """CREATE TABLE IF NOT EXISTS iceberg_tables (
  catalog_name VARCHAR(255) NOT NULL,
  table_namespace VARCHAR(255) NOT NULL,
  table_name VARCHAR(255) NOT NULL,
  metadata_location VARCHAR(1000),
  previous_metadata_location VARCHAR(1000),
  iceberg_type VARCHAR(5),
  PRIMARY KEY (catalog_name, table_namespace, table_name))""",
    """CREATE TABLE IF NOT EXISTS iceberg_namespace_properties (
  catalog_name VARCHAR(255) NOT NULL,
  namespace VARCHAR(255) NOT NULL,
  property_key VARCHAR(255),
  property_value VARCHAR(1000),
  PRIMARY KEY (catalog_name, namespace, property_key))""",
)

# Migrações do registro `nb_*`: índice i leva `user_version` de i para i+1.
_NB_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        """CREATE TABLE IF NOT EXISTS nb_namespaces (
  catalog_name TEXT NOT NULL CHECK (catalog_name = 'spark_catalog'),
  namespace    TEXT NOT NULL,
  location     TEXT,
  created_at   TEXT NOT NULL,
  PRIMARY KEY (catalog_name, namespace))""",
        """CREATE TABLE IF NOT EXISTS nb_tables (
  catalog_name   TEXT NOT NULL CHECK (catalog_name = 'spark_catalog'),
  namespace      TEXT NOT NULL,
  table_name     TEXT NOT NULL,
  format         TEXT NOT NULL CHECK (format IN ('delta','parquet')),
  location       TEXT NOT NULL,
  table_type     TEXT NOT NULL CHECK (table_type IN ('MANAGED','EXTERNAL')),
  columns_json   TEXT NOT NULL,
  partition_cols TEXT NOT NULL DEFAULT '[]',
  options_json   TEXT NOT NULL DEFAULT '{}',
  delta_version  INTEGER,
  description    TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  PRIMARY KEY (catalog_name, namespace, table_name))""",
        "CREATE INDEX IF NOT EXISTS nb_tables_location ON nb_tables(location)",
        "CREATE TABLE IF NOT EXISTS nb_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "INSERT OR IGNORE INTO nb_meta (key, value) VALUES ('generation', '0')",
    ),
)


def catalog_db_path(home: Path) -> Path:
    return home / CATALOG_DB


def connect(home: Path) -> sqlite3.Connection:
    """Abre o `catalog.db` em autocommit (transações são explícitas, `BEGIN IMMEDIATE`)."""
    conn = sqlite3.connect(catalog_db_path(home), isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_catalog_db(home: Path) -> None:
    """Cria/migra o `catalog.db`; idempotente e seguro com partidas concorrentes. Levanta `sqlite3.Error`."""
    conn = connect(home)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in _ICEBERG_DDL:
                conn.execute(statement)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for target, statements in enumerate(_NB_MIGRATIONS[version:], start=version + 1):
                for statement in statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version={target}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
