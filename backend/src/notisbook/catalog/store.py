"""Criação e conexão do `catalog.db`: registro `nb_*` do Notisbook, tabelas do Iceberg JdbcCatalog e catálogo `glue_*`.

O backend é o único que cria/altera tabelas. O DDL `iceberg_*` replica o que o `JdbcCatalog` do
Iceberg 1.10.1 (schema V1) cria, mas com `IF NOT EXISTS`, para que kernels concorrentes não disputem a criação.
O DDL `glue_*` guarda o payload do AWS Glue (JSON) para o endpoint Glue responder como a AWS; também é idempotente.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..notislake import locations
from .registry import DEFAULT_DATABASE

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

# Catálogo `glue`: o payload do Glue (StorageDescriptor, Parameters...) fica em JSON para voltar no GetTable como foi
# gravado. `location` é a forma canônica (`s3a://`, sem `/` final) usada só nas checagens de sobreposição.
# Datas em segundos desde a época (o protocolo Glue serializa timestamps assim).
_GLUE_DDL = (
    """CREATE TABLE IF NOT EXISTS glue_databases (
  name         TEXT PRIMARY KEY,
  description  TEXT,
  location_uri TEXT,
  parameters   TEXT NOT NULL DEFAULT '{}',
  create_time  REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS glue_tables (
  database_name      TEXT NOT NULL,
  name               TEXT NOT NULL,
  table_type         TEXT NOT NULL DEFAULT 'EXTERNAL_TABLE',
  description        TEXT,
  storage_descriptor TEXT NOT NULL DEFAULT '{}',
  partition_keys     TEXT NOT NULL DEFAULT '[]',
  parameters         TEXT NOT NULL DEFAULT '{}',
  extra              TEXT NOT NULL DEFAULT '{}',
  location           TEXT,
  create_time        REAL NOT NULL,
  update_time        REAL NOT NULL,
  version_id         INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (database_name, name))""",
    "CREATE INDEX IF NOT EXISTS glue_tables_location ON glue_tables(location)",
    """CREATE TABLE IF NOT EXISTS glue_partitions (
  database_name      TEXT NOT NULL,
  table_name         TEXT NOT NULL,
  values_json        TEXT NOT NULL,
  storage_descriptor TEXT NOT NULL DEFAULT '{}',
  parameters         TEXT NOT NULL DEFAULT '{}',
  create_time        REAL NOT NULL,
  PRIMARY KEY (database_name, table_name, values_json))""",
)

# Schemas que um catalog.db novo recebe como schemas comuns (o dev pode apagá-los; não voltam).
INITIAL_SCHEMAS = (DEFAULT_DATABASE, "bronze", "silver", "gold")
_INITIAL_SQL = "(" + ", ".join(f"'{name}'" for name in INITIAL_SCHEMAS) + ")"

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
    # O SQLite não altera CHECK: recria `nb_tables` para aceitar `hudi` e acrescentar `hudi_instant`.
    (
        """CREATE TABLE nb_tables_v2 (
  catalog_name   TEXT NOT NULL CHECK (catalog_name = 'spark_catalog'),
  namespace      TEXT NOT NULL,
  table_name     TEXT NOT NULL,
  format         TEXT NOT NULL CHECK (format IN ('delta','parquet','hudi')),
  location       TEXT NOT NULL,
  table_type     TEXT NOT NULL CHECK (table_type IN ('MANAGED','EXTERNAL')),
  columns_json   TEXT NOT NULL,
  partition_cols TEXT NOT NULL DEFAULT '[]',
  options_json   TEXT NOT NULL DEFAULT '{}',
  delta_version  INTEGER,
  description    TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  hudi_instant   TEXT,
  PRIMARY KEY (catalog_name, namespace, table_name))""",
        """INSERT INTO nb_tables_v2 (catalog_name, namespace, table_name, format, location, table_type,
  columns_json, partition_cols, options_json, delta_version, description, created_at, updated_at)
  SELECT catalog_name, namespace, table_name, format, location, table_type,
  columns_json, partition_cols, options_json, delta_version, description, created_at, updated_at
  FROM nb_tables""",
        "DROP TABLE nb_tables",
        "ALTER TABLE nb_tables_v2 RENAME TO nb_tables",
        "CREATE INDEX IF NOT EXISTS nb_tables_location ON nb_tables(location)",
    ),
    # Coluna de exibição do antigo nó `hudi`. O `INSERT` do hook, que não cita a coluna, assume `spark_catalog`.
    (
        "ALTER TABLE nb_namespaces ADD COLUMN display_catalog TEXT NOT NULL DEFAULT 'spark_catalog' "
        "CHECK (display_catalog IN ('spark_catalog','hudi'))",
    ),
    # O nó `hudi` deixou de existir. Só o UPDATE: a coluna e o CHECK ficam inertes para o binário anterior ainda ler.
    (
        "UPDATE nb_namespaces SET display_catalog = 'spark_catalog' WHERE display_catalog = 'hudi'",
    ),
    # Tabelas gerenciadas e schemas no bucket reservado: fila de exclusões e ajuste dos metadados legados (que
    # apontavam para `notislake/<camada>`, onde o DROP de um schema apagaria também as tabelas externas).
    (
        """CREATE TABLE IF NOT EXISTS nb_pending_deletions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  catalog    TEXT NOT NULL,
  namespace  TEXT NOT NULL,
  table_name TEXT NOT NULL,
  location   TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  attempts   INTEGER NOT NULL DEFAULT 0,
  last_error TEXT)""",
        f"UPDATE nb_namespaces SET location = 's3://{locations.MANAGED_BUCKET}/' || namespace WHERE location IS NULL",
        f"""UPDATE glue_databases SET location_uri = 's3://{locations.MANAGED_BUCKET}/' || name
  WHERE name IN {_INITIAL_SQL}
  AND (location_uri IS NULL OR rtrim(location_uri, '/') IN ('s3://{locations.BUCKET}/' || name, 's3a://{locations.BUCKET}/' || name))""",
        "UPDATE nb_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'generation'",
    ),
    # O tipo passou a derivar da location: a EXTERNAL gravada na própria pasta gerenciada (reidratada por `createTable`
    # com path, que o Spark vê como EXTERNAL) vira MANAGED. A generation sobe para as sessões abertas relerem o tipo.
    (
        f"""UPDATE nb_tables SET table_type = 'MANAGED', updated_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
  WHERE catalog_name = 'spark_catalog' AND table_type = 'EXTERNAL'
  AND location = 's3a://{locations.MANAGED_BUCKET}/' || namespace || '/' || table_name""",
        "UPDATE nb_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'generation'",
    ),
    # Mesma regra no `glue`: a não-Iceberg na própria pasta gerenciada é MANAGED_TABLE e sem `Parameters.EXTERNAL`
    # (o Hive decide o DROP por ele). O Iceberg do glue_catalog continua EXTERNAL_TABLE. Sem `generation`: não é `nb_tables`.
    (
        f"""UPDATE glue_tables SET table_type = 'MANAGED_TABLE', parameters = json_remove(parameters, '$.EXTERNAL')
  WHERE location = 's3a://{locations.MANAGED_BUCKET}/' || database_name || '/' || name
  AND upper(coalesce(json_extract(parameters, '$.table_type'), '')) <> 'ICEBERG'
  AND (table_type <> 'MANAGED_TABLE' OR json_extract(parameters, '$.EXTERNAL') IS NOT NULL)""",
    ),
    # A MANAGED_TABLE legada fora da própria pasta (regra antiga `notislake/<camada>/<tabela>`, ou sem location) teria a
    # pasta apagada pelo DROP do Hive: vira EXTERNAL_TABLE com `Parameters.EXTERNAL=TRUE`. `IS NOT` cobre location NULL.
    (
        f"""UPDATE glue_tables SET table_type = 'EXTERNAL_TABLE', parameters = json_set(parameters, '$.EXTERNAL', 'TRUE')
  WHERE table_type = 'MANAGED_TABLE'
  AND upper(coalesce(json_extract(parameters, '$.table_type'), '')) <> 'ICEBERG'
  AND location IS NOT 's3a://{locations.MANAGED_BUCKET}/' || database_name || '/' || name""",
    ),
)


def _seed_initial_schemas(conn: sqlite3.Connection) -> None:
    """Semeia `default`, `bronze`, `silver` e `gold` nos registros `nb_*` e `glue`, em `s3://notisbook-managed/<nome>`.

    Só roda quando o catalog.db acaba de ser criado: um schema apagado depois não volta. Idempotente pela chave
    primária. Dentro de transação.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    created = datetime.now(timezone.utc).timestamp()
    inserted = 0
    for name in INITIAL_SCHEMAS:
        location = locations.schema_location(name, "s3")
        inserted += conn.execute(
            "INSERT OR IGNORE INTO nb_namespaces (catalog_name, namespace, location, created_at) "
            "VALUES ('spark_catalog', ?, ?, ?)",
            (name, location, stamp),
        ).rowcount
        conn.execute(
            "INSERT OR IGNORE INTO glue_databases (name, description, location_uri, parameters, create_time) "
            "VALUES (?, NULL, ?, '{}', ?)",
            (name, location, created),
        )
    if inserted:
        conn.execute("UPDATE nb_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'generation'")


def catalog_db_path(home: Path) -> Path:
    return home / CATALOG_DB


def connect(home: Path) -> sqlite3.Connection:
    """Abre o `catalog.db` em autocommit (transações são explícitas, `BEGIN IMMEDIATE`)."""
    conn = sqlite3.connect(catalog_db_path(home), isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def immediate(conn: sqlite3.Connection) -> Iterator[None]:
    """Transação de escrita (`BEGIN IMMEDIATE`): COMMIT ao sair, ROLLBACK se levantar. A conexão deve estar em autocommit."""
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


def ensure_catalog_db(home: Path) -> None:
    """Cria/migra o `catalog.db` e, só se for novo, semeia os schemas iniciais; idempotente e seguro com partidas concorrentes. Levanta `sqlite3.Error`."""
    conn = connect(home)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in (*_ICEBERG_DDL, *_GLUE_DDL):
                conn.execute(statement)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            has_registry = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'nb_namespaces'").fetchone()
            fresh = version == 0 and has_registry is None
            for target, statements in enumerate(_NB_MIGRATIONS[version:], start=version + 1):
                for statement in statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version={target}")
            if fresh:
                _seed_initial_schemas(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
