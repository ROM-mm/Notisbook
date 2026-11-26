"""Camada de acesso ao catálogo `glue` (`glue_databases`, `glue_tables`, `glue_partitions`) no `catalog.db`.

Guarda o payload do AWS Glue sem reinterpretá-lo (StorageDescriptor, Parameters... em JSON) para o GetTable devolver
o que o notebook gravou. As funções recebem uma conexão e NÃO abrem transação: escrita roda dentro de `writer(home)`
(`BEGIN IMMEDIATE`, único escritor) e leitura em `reader(home)`. Os dicts de saída usam as chaves PascalCase do Glue;
datas saem em segundos desde a época. Nomes de database/tabela são gravados em minúsculas, como o Glue faz.
Regras: o `default` existe sempre e não se exclui; `<schema>.<tabela>` é único entre `nb_*`, `iceberg_*` e `glue_*`, e a
location (gravada como veio e checada em forma `s3a` sem `/` final) não se sobrepõe à de outra tabela de nenhum dos
três nem cai em pasta com exclusão pendente. O tipo deriva da location, não do cliente: tabela não-Iceberg em
`s3://notisbook-managed/<database>/<tabela>` (o DROP do cliente Hive apaga a pasta) é `MANAGED_TABLE`, sem
`Parameters.EXTERNAL`; as demais são externas. O `metadata_location` Iceberg no bucket reservado fica na própria pasta. O `LocationUri` de um database, quando
informado, é sempre `s3://notisbook-managed/<database>` (`schema_location_not_managed`); sem ele segue NULL. O
DeleteDatabase é recusado se alguma tabela de qualquer catálogo está na pasta (a JVM apaga o `LocationUri` inteiro).
Tabelas e partições saem com os campos que os clientes Java do Glue desreferenciam sem checar nulo (flags,
`Retention`, listas e mapas).
Erros: `GlueEntityNotFound`, `GlueAlreadyExists`, `GlueInvalidInput`.
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
from .names import NAME_RE
from .registry import DEFAULT_DATABASE, ERR_NAME_IN_OTHER_CATALOG, pending_locations, table_name_exists
from .store import catalog_db_path, connect, ensure_catalog_db, immediate

GLUE_CATALOG = "glue"
TABLE_TYPE_EXTERNAL = "EXTERNAL_TABLE"
TABLE_TYPE_MANAGED = "MANAGED_TABLE"
_TABLE_TYPES = frozenset({TABLE_TYPE_EXTERNAL, TABLE_TYPE_MANAGED})
# Teto por blob JSON gravado: evita que uma requisição única encha o `catalog.db`.
MAX_JSON_BYTES = 1024 * 1024
# O GlueCatalog do Iceberg grava estes dois Parameters; a tabela Iceberg é sempre EXTERNAL_TABLE.
_ICEBERG_TYPE_PARAM = "table_type"
_ICEBERG_METADATA_PARAM = "metadata_location"
# Campos do TableInput com coluna própria; o resto (Owner, Retention...) vai em `extra`.
_TABLE_FIELDS = frozenset({"Name", "Description", "StorageDescriptor", "PartitionKeys", "TableType", "Parameters"})
# Preenchidos pelo servidor: não são aceitos de volta do cliente.
_SERVER_FIELDS = frozenset({"DatabaseName", "CreateTime", "UpdateTime", "VersionId", "CatalogId", "CreatedBy"})
_TABLE_COLUMNS = (
    "database_name, name, table_type, description, storage_descriptor, partition_keys, parameters, extra, "
    "create_time, update_time, version_id"
)
# Campos do StorageDescriptor que o cliente Java lê como valor primitivo ou coleção, sem tratar ausência (NPE).
_DESCRIPTOR_DEFAULTS: dict[str, Callable[[], Any]] = {
    "Compressed": lambda: False,
    "StoredAsSubDirectories": lambda: False,
    "NumberOfBuckets": lambda: 0,
    "Columns": list,
    "BucketColumns": list,
    "SortColumns": list,
    "Parameters": dict,
}
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


def _complete_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Cópia do StorageDescriptor com os campos ausentes ou nulos preenchidos; o que o cliente enviou é mantido."""
    out = dict(descriptor)
    for key, default in _DESCRIPTOR_DEFAULTS.items():
        if out.get(key) is None:
            out[key] = default()
    serde = out.get("SerdeInfo")
    if isinstance(serde, dict) and serde.get("Parameters") is None:
        out["SerdeInfo"] = {**serde, "Parameters": {}}
    return out


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
    """Todos os databases, por nome."""
    rows = conn.execute("SELECT name, description, location_uri, parameters, create_time FROM glue_databases").fetchall()
    rows.sort(key=lambda r: r[0])
    return [_database_dict(r) for r in rows]


def _folder_in_use(conn: sqlite3.Connection, location_uri: str) -> bool:
    """Alguma tabela de qualquer catálogo (registro, Iceberg ou `glue`) está dentro da pasta `location_uri`.

    Excluir o database apagaria essa pasta (a JVM apaga o `LocationUri` inteiro), levando junto as tabelas.
    """
    tables = [*iceberg_jdbc.known_table_locations(conn), *table_locations(conn)]
    return any(locations.within(_to_s3a(table), _to_s3a(location_uri)) for table in tables)


def _checked_location_uri(location_uri: str | None, database: str) -> str | None:
    """`LocationUri` de Create/UpdateDatabase: vazio vira `None`; senão precisa ser `s3://notisbook-managed/<database>`.

    A gerenciada herda a location do database; outra pasta faria o DROP apagar arquivos que não são do app.
    """
    if not location_uri:
        return None
    if not locations.schema_location_matches(database, location_uri):
        raise GlueInvalidInput("schema_location_not_managed", "LocationUri must be s3://notisbook-managed/<database>.")
    return location_uri


def create_database(conn: sqlite3.Connection, database_input: Any) -> dict[str, Any]:
    """Cria o database a partir do DatabaseInput. Levanta `GlueAlreadyExists`, `GlueInvalidInput`.

    `LocationUri` diferente de `s3://notisbook-managed/<database>` é recusado; sem ele o campo fica NULL.
    """
    payload = _require_object(database_input)
    key = _name(payload.get("Name"))
    description = _optional_text(payload, "Description")
    raw_location = _optional_text(payload, "LocationUri")
    parameters = _dump(_string_map(payload, "Parameters"))
    if _database_row(conn, key) is not None:
        raise GlueAlreadyExists("database_exists", f"Database {key} already exists.")
    location_uri = _checked_location_uri(raw_location, key)
    conn.execute(
        "INSERT INTO glue_databases (name, description, location_uri, parameters, create_time) VALUES (?, ?, ?, ?, ?)",
        (key, description, location_uri, parameters, time.time()),
    )
    return get_database(conn, key)


def update_database(conn: sqlite3.Connection, name: Any, database_input: Any) -> None:
    """Substitui descrição, `LocationUri` e `Parameters` (como o UpdateDatabase); o nome não muda.

    O `LocationUri` segue a regra do CreateDatabase, exceto quando é o mesmo já gravado (ALTER DATABASE ... SET
    DBPROPERTIES o reenvia). O `default` mantém o `LocationUri`: omiti-lo o preserva. Levanta `GlueEntityNotFound` e
    `GlueInvalidInput`.
    """
    key = _require_database(conn, name)
    payload = _require_object(database_input)
    if _name(payload.get("Name")) != key:
        raise GlueInvalidInput("database_rename", "A database cannot be renamed.")
    description = _optional_text(payload, "Description")
    raw_location = _optional_text(payload, "LocationUri")
    parameters = _dump(_string_map(payload, "Parameters"))
    current = conn.execute("SELECT location_uri FROM glue_databases WHERE name = ?", (key,)).fetchone()[0]
    same = bool(raw_location) and current is not None and _to_s3a(raw_location).rstrip("/") == _to_s3a(current).rstrip("/")
    if key == DEFAULT_DATABASE and not raw_location:
        location_uri = current
    else:
        location_uri = current if same else _checked_location_uri(raw_location, key)
    conn.execute(
        "UPDATE glue_databases SET description = ?, location_uri = ?, parameters = ? WHERE name = ?",
        (description, location_uri, parameters, key),
    )


def delete_database(conn: sqlite3.Connection, name: Any) -> None:
    """Remove o database vazio (só a linha; o backend não apaga no bucket).

    Recusa (`GlueInvalidInput`) o `default`, o database com tabelas e o que tem na pasta tabela de qualquer catálogo:
    o DROP do cliente Hive/Spark apaga o `LocationUri` inteiro depois que o DeleteDatabase é aceito.
    """
    key = _require_database(conn, name)
    if key == DEFAULT_DATABASE:
        raise GlueInvalidInput("protected_database", f"Database {key} cannot be deleted.")
    if conn.execute("SELECT 1 FROM glue_tables WHERE database_name = ? LIMIT 1", (key,)).fetchone() is not None:
        raise GlueInvalidInput("database_not_empty", f"Database {key} still has tables.")
    location_uri = conn.execute("SELECT location_uri FROM glue_databases WHERE name = ?", (key,)).fetchone()[0]
    if location_uri and _folder_in_use(conn, location_uri):
        raise GlueInvalidInput("schema_folder_in_use", f"The folder of database {key} contains tables of another catalog.")
    conn.execute("DELETE FROM glue_databases WHERE name = ?", (key,))


def _table_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    database, name, table_type, description, descriptor, keys, parameters, extra, created, updated, version = row
    out: dict[str, Any] = json.loads(extra)
    out.update(
        {
            "Name": name,
            "DatabaseName": database,
            "TableType": table_type,
            "StorageDescriptor": _complete_descriptor(json.loads(descriptor)),
            "PartitionKeys": json.loads(keys),
            "Parameters": json.loads(parameters),
            "CreateTime": created,
            "UpdateTime": updated,
            "VersionId": str(version),
            "IsRegisteredWithLakeFormation": False,
            "IsMaterializedView": False,
        }
    )
    out.setdefault("Retention", 0)
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


def _is_iceberg(parameters: dict[str, str]) -> bool:
    return parameters.get(_ICEBERG_TYPE_PARAM, "").upper() == "ICEBERG"


def _check_iceberg(table_type: str, parameters: dict[str, str]) -> None:
    """Tabela Iceberg (`table_type=ICEBERG`): EXTERNAL_TABLE com `metadata_location` numa location s3 válida."""
    if not _is_iceberg(parameters):
        return
    if table_type != TABLE_TYPE_EXTERNAL:
        raise GlueInvalidInput("iceberg_not_external", f"An Iceberg table must be {TABLE_TYPE_EXTERNAL}.")
    metadata = parameters.get(_ICEBERG_METADATA_PARAM)
    if not metadata:
        raise GlueInvalidInput("missing_metadata_location", "An Iceberg table needs metadata_location.")
    try:
        locations.parse_location(_to_s3a(metadata))
    except locations.InvalidLocation as exc:
        raise GlueInvalidInput(exc.code, f"metadata_location refused ({exc.code}).") from None


def _parse_table_input(table_input: Any) -> dict[str, Any]:
    payload = _require_object(table_input)
    table_type = payload.get("TableType") or TABLE_TYPE_EXTERNAL
    if not isinstance(table_type, str) or table_type not in _TABLE_TYPES:
        raise GlueInvalidInput("unsupported_table_type", f"Only {TABLE_TYPE_EXTERNAL} and {TABLE_TYPE_MANAGED} are supported.")
    keys = payload.get("PartitionKeys")
    if keys is None:
        keys = []
    if not isinstance(keys, list) or not all(isinstance(k, dict) for k in keys):
        raise GlueInvalidInput("invalid_payload", "PartitionKeys must be a list of columns")
    parameters = _string_map(payload, "Parameters")
    _check_iceberg(table_type, parameters)
    extra = {k: v for k, v in payload.items() if k not in _TABLE_FIELDS and k not in _SERVER_FIELDS}
    return {
        "name": _name(payload.get("Name")),
        "table_type": table_type,
        "description": _optional_text(payload, "Description"),
        "descriptor": _dict_field(payload, "StorageDescriptor"),
        "keys": keys,
        "parameters": parameters,
        "extra": extra,
    }


def _to_s3a(uri: str) -> str:
    """`s3://` vira `s3a://`; outros esquemas, `s3n://` inclusive, seguem e são recusados por `parse_location`."""
    scheme, sep, rest = uri.partition("://")
    return f"{locations.SCHEME}://{rest}" if sep and scheme.lower() == "s3" else uri


def _descriptor_location(descriptor: dict[str, Any]) -> str | None:
    raw = descriptor.get("Location")
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise GlueInvalidInput("invalid_payload", "Location must be a string")
    return _to_s3a(raw)


def _canonical_location(
    conn: sqlite3.Connection, database: str, table: str, descriptor: dict[str, Any], table_type: str
) -> str | None:
    """Location canônica validada pela regra de destino (bucket reservado, sem sobreposição); `None` sem Location.

    Ignora a própria tabela na sobreposição, o que serve ao UpdateTable. `MANAGED_TABLE` exige Location e que ela
    seja exatamente `s3://notisbook-managed/<database>/<tabela>`: o DROP do cliente Hive apaga a pasta, então outro
    local poderia apagar os dados de outra tabela.
    """
    location = _descriptor_location(descriptor)
    managed = table_type == TABLE_TYPE_MANAGED
    if location is None:
        if managed:
            raise GlueInvalidInput("managed_location_required", "A managed table needs its Location.")
        return None
    known = [*iceberg_jdbc.known_table_locations(conn), *table_locations(conn, skip=(database, table))]
    try:
        canonical = locations.table_destination(database, table, location, known, None, pending_locations(conn))
    except locations.InvalidLocation as exc:
        raise GlueInvalidInput(exc.code, f"Table location refused ({exc.code}).") from None
    if managed and canonical != locations.managed_location(database, table):
        raise GlueInvalidInput("managed_location_mismatch", "A managed table must be at s3://notisbook-managed/<database>/<table>.")
    return canonical


def _derived_type(database: str, table: str, location: str | None, parameters: dict[str, str]) -> str:
    """Tipo gravado: MANAGED_TABLE só para não-Iceberg na própria pasta gerenciada; o resto (Iceberg inclusive) é EXTERNAL_TABLE."""
    if _is_iceberg(parameters) or location is None:
        return TABLE_TYPE_EXTERNAL
    return TABLE_TYPE_MANAGED if locations.is_own_managed(database, table, location) else TABLE_TYPE_EXTERNAL


def _parameters_for(table_type: str, parameters: dict[str, str]) -> dict[str, str]:
    """Parameters a gravar: a tabela MANAGED não leva `EXTERNAL`, que o Hive leria como tabela externa e não apagaria a pasta."""
    if table_type != TABLE_TYPE_MANAGED:
        return parameters
    return {k: v for k, v in parameters.items() if k.upper() != "EXTERNAL"}


def _require_metadata_inside(
    database: str, table: str, location: str | None, parameters: dict[str, str]
) -> None:
    """Iceberg com `metadata_location` no bucket reservado: tem de estar na pasta da própria tabela.

    O DROP do Hive apaga a pasta da tabela; um metadata na pasta de outra tabela a levaria junto. Sem Location,
    vale a pasta gerenciada da própria chave.
    """
    if not _is_iceberg(parameters):
        return
    metadata = _to_s3a(parameters.get(_ICEBERG_METADATA_PARAM, ""))
    if not locations.targets_managed(metadata):
        return
    own = location if location is not None else locations.managed_location(database, table)
    if not locations.within(metadata, own):
        raise GlueInvalidInput("metadata_outside_location", "metadata_location must be inside the table location.")


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
    """Cria a tabela a partir do TableInput (`version_id` = 1) e a devolve.

    Levanta `GlueEntityNotFound` (database), `GlueAlreadyExists` (nome no `glue`) e `GlueInvalidInput`
    (nome em outro catálogo, location recusada, MANAGED fora do local fixo, Iceberg sem `metadata_location` ou com ele
    na pasta de outra tabela, TableType fora do escopo, payload inválido). O tipo gravado deriva da location.
    """
    db_key = _require_database(conn, database)
    fields = _parse_table_input(table_input)
    name = fields["name"]
    if _table_row(conn, db_key, name) is not None:
        raise GlueAlreadyExists("table_exists", f"Table {name} already exists.")
    _require_free_name(conn, db_key, name)
    location = _canonical_location(conn, db_key, name, fields["descriptor"], fields["table_type"])
    _require_metadata_inside(db_key, name, location, fields["parameters"])
    table_type = _derived_type(db_key, name, location, fields["parameters"])
    now = time.time()
    conn.execute(
        "INSERT INTO glue_tables (database_name, name, table_type, description, storage_descriptor, partition_keys, "
        "parameters, extra, location, create_time, update_time, version_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            db_key,
            name,
            table_type,
            fields["description"],
            _dump(fields["descriptor"]),
            _dump(fields["keys"]),
            _dump(_parameters_for(table_type, fields["parameters"])),
            _dump(fields["extra"]),
            location,
            now,
            now,
        ),
    )
    return get_table(conn, db_key, name)


def _require_partitions_inside(conn: sqlite3.Connection, database: str, table: str, location: str | None) -> None:
    """Toda partição com `Location` da tabela cabe na nova `location` (que não pode ser removida nesse caso)."""
    rows = conn.execute(
        "SELECT storage_descriptor FROM glue_partitions WHERE database_name = ? AND table_name = ?", (database, table)
    ).fetchall()
    for (descriptor,) in rows:
        raw = json.loads(descriptor).get("Location")
        if isinstance(raw, str) and raw and (location is None or not locations.within(_to_s3a(raw), location)):
            raise GlueInvalidInput("table_location_excludes_partitions", "Table location must contain its partition locations.")


def update_table(conn: sqlite3.Connection, database: str, table_input: Any) -> dict[str, Any]:
    """Substitui a definição (como o UpdateTable) e incrementa `version_id`; `create_time` é preservado.

    O `Name` do TableInput identifica a tabela (renomear não existe no Glue). Levanta as mesmas exceções de `create_table`,
    com `GlueEntityNotFound` também para a tabela. Trocar para MANAGED_TABLE fora do local fixo é recusado, bem como
    remover ou trocar a `Location` deixando partição fora dela. O tipo gravado deriva da location (ver `_derived_type`).
    """
    db_key = _require_database(conn, database)
    fields = _parse_table_input(table_input)
    name = fields["name"]
    if _table_row(conn, db_key, name) is None:
        raise GlueEntityNotFound("table_not_found", f"Table {name} not found.")
    location = _canonical_location(conn, db_key, name, fields["descriptor"], fields["table_type"])
    _require_metadata_inside(db_key, name, location, fields["parameters"])
    _require_partitions_inside(conn, db_key, name, location)
    table_type = _derived_type(db_key, name, location, fields["parameters"])
    conn.execute(
        "UPDATE glue_tables SET table_type = ?, description = ?, storage_descriptor = ?, partition_keys = ?, parameters = ?, extra = ?, "
        "location = ?, update_time = ?, version_id = version_id + 1 WHERE database_name = ? AND name = ?",
        (
            table_type,
            fields["description"],
            _dump(fields["descriptor"]),
            _dump(fields["keys"]),
            _dump(_parameters_for(table_type, fields["parameters"])),
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
    delete_table_row(conn, db_key, table_key)


def owns_folder(database: str, table: str, location: str | None, *, managed: bool, iceberg: bool) -> bool:
    """A tabela é dona da pasta gerenciada `s3a://notisbook-managed/<database>/<tabela>`.

    Vale para `MANAGED_TABLE` ou Iceberg com `location` exatamente nessa pasta; é o predicado único da prévia de remoção
    e do `drop_behavior` do Table info.
    """
    return location is not None and (managed or iceberg) and locations.is_own_managed(database, table, location)


def find_table_row(
    conn: sqlite3.Connection, database: str, table: str
) -> tuple[str, str, str, str | None, int, float, bool] | None:
    """`(database, tabela, table_type, location, version_id, create_time, is_iceberg)` sem distinção de caixa; `None` se não existe.

    Só leitura, para a remoção pelo painel: `version_id` e `create_time` identificam a linha (a recriação volta a `version_id` 1).
    """
    if not _has_glue_tables(conn):
        return None
    row = conn.execute(
        "SELECT database_name, name, table_type, location, version_id, create_time, "
        "upper(coalesce(json_extract(parameters, '$.table_type'), '')) = 'ICEBERG' FROM glue_tables "
        "WHERE lower(database_name) = lower(?) AND lower(name) = lower(?)",
        (database, table),
    ).fetchone()
    return None if row is None else (row[0], row[1], row[2], row[3], row[4], row[5], bool(row[6]))


def delete_table_row(conn: sqlite3.Connection, database: str, table: str) -> bool:
    """Remove a tabela e as partições pela chave exata; `True` se a tabela existia. Dentro de transação."""
    conn.execute("DELETE FROM glue_partitions WHERE database_name = ? AND table_name = ?", (database, table))
    return conn.execute("DELETE FROM glue_tables WHERE database_name = ? AND name = ?", (database, table)).rowcount > 0


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
        "StorageDescriptor": _complete_descriptor(json.loads(descriptor)),
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
    """Location da partição: exige tabela com `Location` e a partição dentro dela.

    Partição sem `Location` própria é aceita. Com a pasta sempre sob a da tabela, nenhuma pasta de partição escapa
    das regras de sobreposição, que só enxergam a pasta da tabela.
    """
    location = _descriptor_location(descriptor)
    if location is None:
        return
    if table_location is None:
        raise GlueInvalidInput("partition_needs_table_location", "A partition location needs a table with a Location.")
    try:
        canonical = locations.parse_location(location).uri
    except locations.InvalidLocation as exc:
        raise GlueInvalidInput(exc.code, f"Partition location refused ({exc.code}).") from None
    if not locations.within(canonical, table_location):
        raise GlueInvalidInput("partition_outside_table", "Partition location must be inside the table location.")


def batch_create_partitions(
    conn: sqlite3.Connection, database: str, table: str, partition_inputs: Sequence[Any]
) -> list[dict[str, Any]]:
    """Cria as partições e devolve os `Errors` do BatchCreatePartition (vazio se tudo foi criado).

    `Values` repetidos na mesma requisição são deduplicados (vale o primeiro; o GlueContext os repete). Partição que já
    existe vira item `AlreadyExistsException`, sem abortar as demais. Payload malformado, número de `Values` diferente
    do de chaves de partição ou location fora da tabela (ou tabela sem `Location`) levantam `GlueInvalidInput` antes de gravar.
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


def delete_partition(conn: sqlite3.Connection, database: str, table: str, values: Any) -> None:
    """Remove a partição pelos `Values` (só a linha); a inexistente é ignorada, como no `batch_delete_partitions`."""
    db_key, table_key, _, _ = _table_partition_context(conn, database, table)
    conn.execute(
        "DELETE FROM glue_partitions WHERE database_name = ? AND table_name = ? AND values_json = ?",
        (db_key, table_key, _values_key(_partition_values(values))),
    )


def update_partition(conn: sqlite3.Connection, database: str, table: str, values: Any, partition_input: Any) -> None:
    """Substitui a partição `values` pelo PartitionInput; `Values` diferentes no input renomeiam a partição.

    Mesmas regras de location do `batch_create_partitions`. Levanta `GlueEntityNotFound` (partição inexistente),
    `GlueAlreadyExists` (o novo `Values` já existe) e `GlueInvalidInput`.
    """
    db_key, table_key, key_count, table_location = _table_partition_context(conn, database, table)
    old_key = _values_key(_partition_values(values))
    payload = _require_object(partition_input)
    new_values = _partition_values(payload.get("Values", values))
    if len(new_values) != key_count:
        raise GlueInvalidInput("partition_values_mismatch", "Values must match the table partition keys.")
    descriptor = _dict_field(payload, "StorageDescriptor")
    _check_partition_location(descriptor, table_location)
    parameters = _dump(_string_map(payload, "Parameters"))
    new_key = _values_key(new_values)
    exists = "SELECT 1 FROM glue_partitions WHERE database_name = ? AND table_name = ? AND values_json = ?"
    if conn.execute(exists, (db_key, table_key, old_key)).fetchone() is None:
        raise GlueEntityNotFound("partition_not_found", "Partition not found.")
    if new_key != old_key and conn.execute(exists, (db_key, table_key, new_key)).fetchone() is not None:
        raise GlueAlreadyExists("partition_exists", "Partition already exists.")
    conn.execute(
        "UPDATE glue_partitions SET values_json = ?, storage_descriptor = ?, parameters = ? "
        "WHERE database_name = ? AND table_name = ? AND values_json = ?",
        (new_key, _dump(descriptor), parameters, db_key, table_key, old_key),
    )
