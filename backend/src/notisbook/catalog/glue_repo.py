"""Camada de acesso ao catálogo `glue` (`glue_databases`, `glue_tables`, `glue_partitions`) no `catalog.db`.

Guarda o payload do AWS Glue sem reinterpretá-lo (StorageDescriptor, Parameters... em JSON) para o GetTable devolver
o que o notebook gravou. As funções recebem uma conexão e NÃO abrem transação: escrita roda dentro de `writer(home)`
(`BEGIN IMMEDIATE`, único escritor) e leitura em `reader(home)`. Os dicts de saída usam as chaves PascalCase do Glue;
datas saem em segundos desde a época. Nomes de database/tabela são gravados em minúsculas, como o Glue faz.
Regras: as camadas de `locations.LAYERS` existem sempre e não se excluem; `<schema>.<tabela>` é único entre `nb_*`,
`iceberg_*` e `glue_*`, e a location (`s3://notislake/...`, gravada como veio e checada em forma `s3a` sem `/` final)
não se sobrepõe à de outra tabela de nenhum dos três. Erros: `GlueEntityNotFound`, `GlueAlreadyExists`, `GlueInvalidInput`.
"""

import json
import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..notislake import locations
from . import iceberg_jdbc
from .registry import ERR_NAME_IN_OTHER_CATALOG, table_name_exists
from .schemas import NAME_RE
from .store import catalog_db_path, connect, ensure_catalog_db, immediate

GLUE_CATALOG = "glue"
TABLE_TYPE_EXTERNAL = "EXTERNAL_TABLE"
# Teto por blob JSON gravado: evita que uma requisição única encha o `catalog.db`.
MAX_JSON_BYTES = 1024 * 1024
# Delta/Iceberg/Hudi no `glue` estão fora de escopo: a tabela seria registrada, mas o Spark não a leria como esperado.
_UNSUPPORTED_FORMATS = frozenset({"delta", "iceberg", "hudi"})
_FORMAT_PARAMS = ("table_type", "spark.sql.sources.provider")
# Campos do TableInput com coluna própria; o resto (Owner, Retention...) vai em `extra`.
_TABLE_FIELDS = frozenset({"Name", "Description", "StorageDescriptor", "PartitionKeys", "TableType", "Parameters"})
# Preenchidos pelo servidor: não são aceitos de volta do cliente.
_SERVER_FIELDS = frozenset({"DatabaseName", "CreateTime", "UpdateTime", "VersionId", "CatalogId", "CreatedBy"})
_TABLE_COLUMNS = (
    "database_name, name, table_type, description, storage_descriptor, partition_keys, parameters, extra, "
    "create_time, update_time, version_id"
)
_ALREADY_EXISTS = {"ErrorCode": "AlreadyExistsException", "ErrorMessage": "Partition already exists."}


class GlueError(Exception):
    """Base dos erros de domínio; `reason` é categórico (ex.: `table_not_found`, `overlaps_table`)."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = reason


class GlueEntityNotFound(GlueError):
    """Database, tabela ou partição inexistente (EntityNotFoundException)."""


class GlueAlreadyExists(GlueError):
    """Database ou tabela já existe (AlreadyExistsException)."""


class GlueInvalidInput(GlueError):
    """Payload ou regra de catálogo violada (InvalidInputException)."""


@contextmanager
def reader(home: Path) -> Iterator[sqlite3.Connection | None]:
    """Conexão só de leitura; `None` quando o `catalog.db` ainda não existe (o arquivo não é criado)."""
    if not catalog_db_path(home).exists():
        yield None
        return
    conn = connect(home)
    conn.execute("PRAGMA query_only=ON")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def writer(home: Path) -> Iterator[sqlite3.Connection]:
    """Conexão dentro de `BEGIN IMMEDIATE`: COMMIT ao sair, ROLLBACK se levantar. Cria o `catalog.db` se faltar."""
    if not catalog_db_path(home).exists():
        ensure_catalog_db(home)
    conn = connect(home)
    try:
        with immediate(conn):
            yield conn
    finally:
        conn.close()


def _dump(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode()) > MAX_JSON_BYTES:
        raise GlueInvalidInput("payload_too_large")
    return text


def _name(value: Any) -> str:
    if not isinstance(value, str) or NAME_RE.fullmatch(value) is None:
        raise GlueInvalidInput("invalid_name")
    return value.lower()


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise GlueInvalidInput("invalid_payload", f"{key} must be a string")
    return value


def _string_map(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise GlueInvalidInput("invalid_payload", f"{key} must be a map of strings")
    return value


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GlueInvalidInput("invalid_payload", f"{key} must be an object")
    return value


def _require_object(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GlueInvalidInput("invalid_payload")
    return payload


def _database_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    name, description, location_uri, parameters, created = row
    out: dict[str, Any] = {"Name": name, "Parameters": json.loads(parameters), "CreateTime": created}
    if description is not None:
        out["Description"] = description
    if location_uri is not None:
        out["LocationUri"] = location_uri
    return out


def _database_row(conn: sqlite3.Connection, key: str) -> tuple[Any, ...] | None:
    row: tuple[Any, ...] | None = conn.execute(
        "SELECT name, description, location_uri, parameters, create_time FROM glue_databases WHERE name = ?", (key,)
    ).fetchone()
    return row


def _require_database(conn: sqlite3.Connection, name: Any) -> str:
    key = _name(name)
    if conn.execute("SELECT 1 FROM glue_databases WHERE name = ?", (key,)).fetchone() is None:
        raise GlueEntityNotFound("database_not_found", f"Database {key} not found.")
    return key


def get_database(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """Database pelo nome (sem distinção de caixa). Levanta `GlueEntityNotFound`, `GlueInvalidInput`."""
    row = _database_row(conn, _name(name))
    if row is None:
        raise GlueEntityNotFound("database_not_found", f"Database {name} not found.")
    return _database_dict(row)


def list_databases(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Todos os databases: camadas primeiro (na ordem de `LAYERS`), depois os demais por nome."""
    rows = conn.execute("SELECT name, description, location_uri, parameters, create_time FROM glue_databases").fetchall()
    rows.sort(key=lambda r: (locations.layer_rank(r[0]), r[0]))
    return [_database_dict(r) for r in rows]


def create_database(conn: sqlite3.Connection, database_input: Any) -> dict[str, Any]:
    """Cria o database a partir do DatabaseInput. Levanta `GlueAlreadyExists` (inclui as camadas), `GlueInvalidInput`."""
    payload = _require_object(database_input)
    key = _name(payload.get("Name"))
    description = _optional_text(payload, "Description")
    location_uri = _optional_text(payload, "LocationUri")
    parameters = _dump(_string_map(payload, "Parameters"))
    if _database_row(conn, key) is not None:
        raise GlueAlreadyExists("database_exists", f"Database {key} already exists.")
    conn.execute(
        "INSERT INTO glue_databases (name, description, location_uri, parameters, create_time) VALUES (?, ?, ?, ?, ?)",
        (key, description, location_uri, parameters, time.time()),
    )
    return get_database(conn, key)


def _table_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    database, name, table_type, description, descriptor, keys, parameters, extra, created, updated, version = row
    out: dict[str, Any] = json.loads(extra)
    out.update(
        {
            "Name": name,
            "DatabaseName": database,
            "TableType": table_type,
            "StorageDescriptor": json.loads(descriptor),
            "PartitionKeys": json.loads(keys),
            "Parameters": json.loads(parameters),
            "CreateTime": created,
            "UpdateTime": updated,
            "VersionId": str(version),
        }
    )
    if description is not None:
        out["Description"] = description
    return out


def _table_row(conn: sqlite3.Connection, database: str, table: str) -> tuple[Any, ...] | None:
    row: tuple[Any, ...] | None = conn.execute(
        f"SELECT {_TABLE_COLUMNS} FROM glue_tables WHERE database_name = ? AND name = ?", (database, table)
    ).fetchone()
    return row


def _require_table(conn: sqlite3.Connection, database: Any, table: Any) -> tuple[str, str]:
    db_key = _require_database(conn, database)
    table_key = _name(table)
    if _table_row(conn, db_key, table_key) is None:
        raise GlueEntityNotFound("table_not_found", f"Table {table_key} not found.")
    return db_key, table_key


def get_table(conn: sqlite3.Connection, database: str, table: str) -> dict[str, Any]:
    """Tabela como foi gravada (StorageDescriptor intacto). Levanta `GlueEntityNotFound`, `GlueInvalidInput`."""
    db_key = _require_database(conn, database)
    table_key = _name(table)
    row = _table_row(conn, db_key, table_key)
    if row is None:
        raise GlueEntityNotFound("table_not_found", f"Table {table_key} not found.")
    return _table_dict(row)


def list_tables(conn: sqlite3.Connection, database: str) -> list[dict[str, Any]]:
    """Tabelas do database, ordenadas por nome."""
    key = _require_database(conn, database)
    rows = conn.execute(
        f"SELECT {_TABLE_COLUMNS} FROM glue_tables WHERE database_name = ? ORDER BY name", (key,)
    ).fetchall()
    return [_table_dict(r) for r in rows]


def table_locations(conn: sqlite3.Connection, skip: tuple[str, str] | None = None) -> list[str]:
    """Locations canônicas (`s3a`, sem `/` final) das tabelas `glue`, exceto `skip` `(database, table)`.

    Entrada da regra de sobreposição também para os outros catálogos.
    """
    if not _has_glue_tables(conn):
        return []
    rows = conn.execute("SELECT database_name, name, location FROM glue_tables WHERE location IS NOT NULL").fetchall()
    return [loc for db, name, loc in rows if skip is None or (db, name) != skip]


def registry_tables(conn: sqlite3.Connection) -> list[dict[str, str | None]]:
    """Tabelas `glue` como `{"db", "name", "loc"}` (`loc` canônica `s3a` ou `None`) para o `/registry` dos runtimes.

    O hook recusa, antes de gravar, nome ou pasta que o `glue` já usa. Sem as tabelas `glue_*` no `catalog.db`, vazio.
    """
    if not _has_glue_tables(conn):
        return []
    rows = conn.execute("SELECT database_name, name, location FROM glue_tables ORDER BY database_name, name").fetchall()
    return [{"db": db, "name": name, "loc": loc} for db, name, loc in rows]


def _has_glue_tables(conn: sqlite3.Connection) -> bool:
    """`catalog.db` criado antes do `glue` ainda não tem as tabelas até o próximo `ensure_catalog_db`."""
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'glue_tables'").fetchone() is not None


def table_name_exists_in_glue(conn: sqlite3.Connection, database: str, table: str) -> bool:
    """Existe `database.table` no `glue`, sem distinção de caixa (o nome é único entre os catálogos)."""
    if not _has_glue_tables(conn):
        return False
    row = conn.execute(
        "SELECT 1 FROM glue_tables WHERE lower(database_name) = lower(?) AND lower(name) = lower(?)", (database, table)
    ).fetchone()
    return row is not None


def _reject_unsupported_format(parameters: dict[str, str]) -> None:
    for key in _FORMAT_PARAMS:
        if parameters.get(key, "").lower() in _UNSUPPORTED_FORMATS:
            raise GlueInvalidInput("unsupported_format", "Only Parquet, CSV and JSON external tables are supported.")


def _parse_table_input(table_input: Any) -> dict[str, Any]:
    payload = _require_object(table_input)
    table_type = payload.get("TableType") or TABLE_TYPE_EXTERNAL
    if table_type != TABLE_TYPE_EXTERNAL:
        raise GlueInvalidInput("unsupported_table_type", f"Only {TABLE_TYPE_EXTERNAL} tables are supported.")
    keys = payload.get("PartitionKeys")
    if keys is None:
        keys = []
    if not isinstance(keys, list) or not all(isinstance(k, dict) for k in keys):
        raise GlueInvalidInput("invalid_payload", "PartitionKeys must be a list of columns")
    parameters = _string_map(payload, "Parameters")
    _reject_unsupported_format(parameters)
    extra = {k: v for k, v in payload.items() if k not in _TABLE_FIELDS and k not in _SERVER_FIELDS}
    return {
        "name": _name(payload.get("Name")),
        "description": _optional_text(payload, "Description"),
        "descriptor": _dict_field(payload, "StorageDescriptor"),
        "keys": keys,
        "parameters": parameters,
        "extra": extra,
    }


def _to_s3a(uri: str) -> str:
    """`s3://` vira `s3a://`; outros esquemas, `s3n://` inclusive, seguem e são recusados por `parse_notislake`."""
    scheme, sep, rest = uri.partition("://")
    return f"{locations.SCHEME}://{rest}" if sep and scheme.lower() == "s3" else uri


def _descriptor_location(descriptor: dict[str, Any]) -> str | None:
    raw = descriptor.get("Location")
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise GlueInvalidInput("invalid_payload", "Location must be a string")
    return _to_s3a(raw)


def _canonical_location(conn: sqlite3.Connection, database: str, table: str, descriptor: dict[str, Any]) -> str | None:
    """Location canônica validada pela regra do notislake (camada do schema, sem sobreposição); `None` sem Location.

    Ignora a própria tabela na sobreposição, o que serve ao UpdateTable.
    """
    location = _descriptor_location(descriptor)
    if location is None:
        return None
    known = [*iceberg_jdbc.known_table_locations(conn), *table_locations(conn, skip=(database, table))]
    try:
        return locations.table_destination(database, table, location, known)
    except locations.InvalidLocation as exc:
        raise GlueInvalidInput(exc.code, f"Table location refused ({exc.code}).") from None


def _iceberg_name_exists(conn: sqlite3.Connection, database: str, table: str) -> bool:
    """Existe tabela ou view Iceberg com esse schema e nome, sem distinção de caixa nas duas partes."""
    row = conn.execute(
        "SELECT 1 FROM iceberg_tables WHERE catalog_name = ? AND lower(table_namespace) = lower(?) "
        "AND lower(table_name) = lower(?)",
        (iceberg_jdbc.ICEBERG_CATALOG, database, table),
    ).fetchone()
    return row is not None


def _require_free_name(conn: sqlite3.Connection, database: str, table: str) -> None:
    if table_name_exists(conn, database, table) or _iceberg_name_exists(conn, database, table):
        raise GlueInvalidInput(ERR_NAME_IN_OTHER_CATALOG, "A table with this schema and name exists in another catalog.")


def create_table(conn: sqlite3.Connection, database: str, table_input: Any) -> dict[str, Any]:
    """Cria a tabela externa a partir do TableInput (`version_id` = 1) e a devolve.

    Levanta `GlueEntityNotFound` (database), `GlueAlreadyExists` (nome no `glue`) e `GlueInvalidInput`
    (nome em outro catálogo, location recusada, formato ou TableType fora do escopo, payload inválido).
    """
    db_key = _require_database(conn, database)
    fields = _parse_table_input(table_input)
    name = fields["name"]
    if _table_row(conn, db_key, name) is not None:
        raise GlueAlreadyExists("table_exists", f"Table {name} already exists.")
    _require_free_name(conn, db_key, name)
    location = _canonical_location(conn, db_key, name, fields["descriptor"])
    now = time.time()
    conn.execute(
        "INSERT INTO glue_tables (database_name, name, table_type, description, storage_descriptor, partition_keys, "
        "parameters, extra, location, create_time, update_time, version_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            db_key,
            name,
            TABLE_TYPE_EXTERNAL,
            fields["description"],
            _dump(fields["descriptor"]),
            _dump(fields["keys"]),
            _dump(fields["parameters"]),
            _dump(fields["extra"]),
            location,
            now,
            now,
        ),
    )
    return get_table(conn, db_key, name)


def update_table(conn: sqlite3.Connection, database: str, table_input: Any) -> dict[str, Any]:
    """Substitui a definição (como o UpdateTable) e incrementa `version_id`; `create_time` é preservado.

    O `Name` do TableInput identifica a tabela (renomear não existe no Glue). Levanta as mesmas exceções de `create_table`,
    com `GlueEntityNotFound` também para a tabela.
    """
    db_key = _require_database(conn, database)
    fields = _parse_table_input(table_input)
    name = fields["name"]
    if _table_row(conn, db_key, name) is None:
        raise GlueEntityNotFound("table_not_found", f"Table {name} not found.")
    location = _canonical_location(conn, db_key, name, fields["descriptor"])
    conn.execute(
        "UPDATE glue_tables SET description = ?, storage_descriptor = ?, partition_keys = ?, parameters = ?, extra = ?, "
        "location = ?, update_time = ?, version_id = version_id + 1 WHERE database_name = ? AND name = ?",
        (
            fields["description"],
            _dump(fields["descriptor"]),
            _dump(fields["keys"]),
            _dump(fields["parameters"]),
            _dump(fields["extra"]),
            location,
            time.time(),
            db_key,
            name,
        ),
    )
    return get_table(conn, db_key, name)


def delete_table(conn: sqlite3.Connection, database: str, table: str) -> None:
    """Remove a tabela e as partições (só linhas; arquivos do bucket ficam)."""
    db_key, table_key = _require_table(conn, database, table)
    conn.execute("DELETE FROM glue_partitions WHERE database_name = ? AND table_name = ?", (db_key, table_key))
    conn.execute("DELETE FROM glue_tables WHERE database_name = ? AND name = ?", (db_key, table_key))


def _partition_values(values: Any) -> list[str]:
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
        raise GlueInvalidInput("invalid_partition_values", "Values must be a non-empty list of non-empty strings.")
    return values


def _values_key(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _partition_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    database, table, values, descriptor, parameters, created = row
    return {
        "Values": json.loads(values),
        "DatabaseName": database,
        "TableName": table,
        "CreationTime": created,
        "StorageDescriptor": json.loads(descriptor),
        "Parameters": json.loads(parameters),
    }


def _table_partition_context(conn: sqlite3.Connection, database: Any, table: Any) -> tuple[str, str, int, str | None]:
    """`(database, tabela, nº de chaves de partição, location canônica)` da tabela; levanta `GlueEntityNotFound`."""
    db_key, table_key = _require_table(conn, database, table)
    keys, location = conn.execute(
        "SELECT partition_keys, location FROM glue_tables WHERE database_name = ? AND name = ?", (db_key, table_key)
    ).fetchone()
    return db_key, table_key, len(json.loads(keys)), location


def get_partitions(
    conn: sqlite3.Connection,
    database: str,
    table: str,
    partition_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """Partições da tabela na ordem de criação; `partition_filter` recebe cada partição decodificada, `None` devolve todas."""
    db_key, table_key, _, _ = _table_partition_context(conn, database, table)
    rows = conn.execute(
        "SELECT database_name, table_name, values_json, storage_descriptor, parameters, create_time FROM glue_partitions "
        "WHERE database_name = ? AND table_name = ? ORDER BY rowid",
        (db_key, table_key),
    ).fetchall()
    partitions = [_partition_dict(r) for r in rows]
    return [p for p in partitions if partition_filter(p)] if partition_filter else partitions


def get_partition(conn: sqlite3.Connection, database: str, table: str, values: Any) -> dict[str, Any]:
    """Partição pelos `Values`. Levanta `GlueEntityNotFound`, `GlueInvalidInput`."""
    db_key, table_key, _, _ = _table_partition_context(conn, database, table)
    row = conn.execute(
        "SELECT database_name, table_name, values_json, storage_descriptor, parameters, create_time FROM glue_partitions "
        "WHERE database_name = ? AND table_name = ? AND values_json = ?",
        (db_key, table_key, _values_key(_partition_values(values))),
    ).fetchone()
    if row is None:
        raise GlueEntityNotFound("partition_not_found", "Partition not found.")
    return _partition_dict(row)


def _check_partition_location(descriptor: dict[str, Any], table_location: str | None) -> None:
    location = _descriptor_location(descriptor)
    if location is None:
        return
    try:
        canonical = locations.parse_notislake(location).uri
    except locations.InvalidLocation as exc:
        raise GlueInvalidInput(exc.code, f"Partition location refused ({exc.code}).") from None
    if table_location is not None and not locations.within(canonical, table_location):
        raise GlueInvalidInput("partition_outside_table", "Partition location must be inside the table location.")


def batch_create_partitions(
    conn: sqlite3.Connection, database: str, table: str, partition_inputs: Sequence[Any]
) -> list[dict[str, Any]]:
    """Cria as partições e devolve os `Errors` do BatchCreatePartition (vazio se tudo foi criado).

    `Values` repetidos na mesma requisição são deduplicados (vale o primeiro; o GlueContext os repete). Partição que já
    existe vira item `AlreadyExistsException`, sem abortar as demais. Payload malformado, número de `Values` diferente
    do de chaves de partição ou location fora do notislake/da tabela levantam `GlueInvalidInput` antes de gravar.
    """
    db_key, table_key, key_count, table_location = _table_partition_context(conn, database, table)
    if not isinstance(partition_inputs, list):
        raise GlueInvalidInput("invalid_payload", "PartitionInputList must be a list")
    prepared: dict[str, tuple[list[str], dict[str, Any], dict[str, str]]] = {}
    for item in partition_inputs:
        payload = _require_object(item)
        values = _partition_values(payload.get("Values"))
        if len(values) != key_count:
            raise GlueInvalidInput("partition_values_mismatch", "Values must match the table partition keys.")
        descriptor = _dict_field(payload, "StorageDescriptor")
        _check_partition_location(descriptor, table_location)
        prepared.setdefault(_values_key(values), (values, descriptor, _string_map(payload, "Parameters")))
    errors: list[dict[str, Any]] = []
    now = time.time()
    for values_key, (values, descriptor, parameters) in prepared.items():
        created = conn.execute(
            "INSERT OR IGNORE INTO glue_partitions (database_name, table_name, values_json, storage_descriptor, "
            "parameters, create_time) VALUES (?, ?, ?, ?, ?, ?)",
            (db_key, table_key, values_key, _dump(descriptor), _dump(parameters), now),
        ).rowcount
        if not created:
            errors.append({"PartitionValues": values, "ErrorDetail": dict(_ALREADY_EXISTS)})
    return errors


def batch_delete_partitions(
    conn: sqlite3.Connection, database: str, table: str, values_list: Sequence[Any]
) -> list[dict[str, Any]]:
    """Remove as partições pelos `Values`; as inexistentes são ignoradas (o Glue não as reporta). Devolve os `Errors` (vazio)."""
    db_key, table_key, _, _ = _table_partition_context(conn, database, table)
    if not isinstance(values_list, list):
        raise GlueInvalidInput("invalid_payload", "PartitionsToDelete must be a list")
    keys = [_values_key(_partition_values(_require_object(item).get("Values"))) for item in values_list]
    for values_key in dict.fromkeys(keys):
        conn.execute(
            "DELETE FROM glue_partitions WHERE database_name = ? AND table_name = ? AND values_json = ?",
            (db_key, table_key, values_key),
        )
    return []
