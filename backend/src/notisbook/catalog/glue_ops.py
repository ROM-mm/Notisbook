"""Operações do AWS Glue sobre `glue_repo`: recebem a conexão e o JSON da requisição, devolvem o JSON da resposta.

`READ_OPERATIONS` rodam em `glue_repo.reader`; `WRITE_OPERATIONS`, dentro da transação de `glue_repo.writer`. Os erros
de domínio (`GlueError`) sobem como estão: o endpoint os traduz. Sem `MaxResults` a listagem volta inteira, sem
`NextToken`; com ele, `NextToken` é o deslocamento opaco da próxima página. `CatalogId` é aceito e ignorado.
"""

import re
import sqlite3
from collections.abc import Callable
from typing import Any

from . import glue_repo
from .glue_expression import compile_expression
from .glue_repo import GlueAlreadyExists, GlueInvalidInput

Operation = Callable[[sqlite3.Connection, dict[str, Any]], dict[str, Any]]

MAX_RESULTS_DATABASES = 100
MAX_RESULTS_TABLES = 100
MAX_RESULTS_PARTITIONS = 1000
MAX_BATCH_CREATE_PARTITIONS = 100
MAX_BATCH_DELETE_PARTITIONS = 25
MAX_SEGMENTS = 10
_TOKEN_RE = re.compile(r"\d{1,9}")
# Padrão do GetTables: nomes com `*` e `|`; só estes caracteres, para o padrão nunca virar regex do cliente.
_TABLE_PATTERN_RE = re.compile(r"[A-Za-z0-9_$*|-]{1,512}")


class ConcurrentModification(glue_repo.GlueError):
    """`VersionId` desatualizado no UpdateTable (ConcurrentModificationException)."""

    def __init__(self, message: str) -> None:
        super().__init__("version_mismatch", message)


def _page(items: list[dict[str, Any]], params: dict[str, Any], maximum: int) -> tuple[list[dict[str, Any]], str | None]:
    """Recorta a página de `NextToken`/`MaxResults`; sem `MaxResults` devolve tudo."""
    token = params.get("NextToken")
    if token is None:
        start = 0
    elif isinstance(token, str) and _TOKEN_RE.fullmatch(token):
        start = int(token)
    else:
        raise GlueInvalidInput("invalid_token", "NextToken is not valid.")
    size = params.get("MaxResults")
    if size is None:
        return items[start:], None
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= maximum:
        raise GlueInvalidInput("invalid_max_results", f"MaxResults must be between 1 and {maximum}.")
    end = start + size
    return items[start:end], str(end) if end < len(items) else None


def _with_token(key: str, items: list[dict[str, Any]], token: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {key: items}
    if token is not None:
        out["NextToken"] = token
    return out


def _table_matcher(pattern: Any) -> Callable[[str], bool] | None:
    if pattern is None or pattern == "":
        return None
    if not isinstance(pattern, str) or _TABLE_PATTERN_RE.fullmatch(pattern) is None:
        raise GlueInvalidInput("unsupported_expression", "Unsupported table name pattern.")
    folded = pattern.lower()  # os nomes são gravados em minúsculas; o padrão precisa estar na mesma caixa
    regex = re.compile("|".join(".*".join(re.escape(piece) for piece in alt.split("*")) for alt in folded.split("|")))
    return lambda name: regex.fullmatch(name.lower()) is not None


def _get_database(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    return {"Database": glue_repo.get_database(conn, params.get("Name"))}


def _get_databases(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    page, token = _page(glue_repo.list_databases(conn), params, MAX_RESULTS_DATABASES)
    return _with_token("DatabaseList", page, token)


def _create_database(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.create_database(conn, params.get("DatabaseInput"))
    return {}


def _delete_database(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.delete_database(conn, params.get("Name"))
    return {}


def _update_database(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.update_database(conn, params.get("Name"), params.get("DatabaseInput"))
    return {}


def _get_table(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    return {"Table": glue_repo.get_table(conn, params.get("DatabaseName"), params.get("Name"))}


def _get_tables(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    matches = _table_matcher(params.get("Expression"))
    tables = glue_repo.list_tables(conn, params.get("DatabaseName"))
    if matches is not None:
        tables = [t for t in tables if matches(t["Name"])]
    page, token = _page(tables, params, MAX_RESULTS_TABLES)
    return _with_token("TableList", page, token)


def _create_table(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.create_table(conn, params.get("DatabaseName"), params.get("TableInput"))
    return {}


def _update_table(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    """`VersionId` informado é o bloqueio otimista do Glue: se não for o atual, nada é gravado."""
    database = params.get("DatabaseName")
    table_input = params.get("TableInput")
    expected = params.get("VersionId")
    if expected is not None:
        name = table_input.get("Name") if isinstance(table_input, dict) else None
        current = glue_repo.get_table(conn, database, name)
        if current["VersionId"] != expected:
            raise ConcurrentModification("Table version does not match VersionId.")
    glue_repo.update_table(conn, database, table_input)
    return {}


def _delete_table(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.delete_table(conn, params.get("DatabaseName"), params.get("Name"))
    return {}


def _segment(params: dict[str, Any]) -> tuple[int, int] | None:
    segment = params.get("Segment")
    if segment is None:
        return None
    number = segment.get("SegmentNumber") if isinstance(segment, dict) else None
    total = segment.get("TotalSegments") if isinstance(segment, dict) else None
    ints = all(isinstance(v, int) and not isinstance(v, bool) for v in (number, total))
    if not ints or not 1 <= total <= MAX_SEGMENTS or not 0 <= number < total:
        raise GlueInvalidInput("invalid_segment", "Segment is not valid.")
    return number, total


def _get_partitions(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    database, table = params.get("DatabaseName"), params.get("TableName")
    keys = glue_repo.get_table(conn, database, table)["PartitionKeys"]
    predicate = compile_expression(params.get("Expression"), keys)
    partitions = glue_repo.get_partitions(
        conn, database, table, (lambda p: predicate(p["Values"])) if predicate else None
    )
    segment = _segment(params)
    if segment is not None:
        number, total = segment
        partitions = [p for i, p in enumerate(partitions) if i % total == number]
    page, token = _page(partitions, params, MAX_RESULTS_PARTITIONS)
    return _with_token("Partitions", page, token)


def _get_partition(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    partition = glue_repo.get_partition(
        conn, params.get("DatabaseName"), params.get("TableName"), params.get("PartitionValues")
    )
    return {"Partition": partition}


def _create_partition(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    errors = glue_repo.batch_create_partitions(
        conn, params.get("DatabaseName"), params.get("TableName"), [params.get("PartitionInput")]
    )
    if errors:
        raise GlueAlreadyExists("partition_exists", "Partition already exists.")
    return {}


def _bounded_list(params: dict[str, Any], key: str, limit: int) -> Any:
    value = params.get(key)
    if isinstance(value, list) and len(value) > limit:
        raise GlueInvalidInput("too_many_items", f"{key} accepts at most {limit} items.")
    return value


def _batch_create_partition(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    items = _bounded_list(params, "PartitionInputList", MAX_BATCH_CREATE_PARTITIONS)
    errors = glue_repo.batch_create_partitions(conn, params.get("DatabaseName"), params.get("TableName"), items)
    return {"Errors": errors}


def _batch_delete_partition(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    items = _bounded_list(params, "PartitionsToDelete", MAX_BATCH_DELETE_PARTITIONS)
    errors = glue_repo.batch_delete_partitions(conn, params.get("DatabaseName"), params.get("TableName"), items)
    return {"Errors": errors}


def _delete_partition(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.delete_partition(conn, params.get("DatabaseName"), params.get("TableName"), params.get("PartitionValues"))
    return {}


def _update_partition(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.update_partition(
        conn,
        params.get("DatabaseName"),
        params.get("TableName"),
        params.get("PartitionValueList"),
        params.get("PartitionInput"),
    )
    return {}


def _get_user_defined_functions(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    """Funções definidas pelo usuário não são suportadas: a lista é sempre vazia (o database, se informado, precisa existir)."""
    if params.get("DatabaseName") is not None:
        glue_repo.get_database(conn, params["DatabaseName"])
    return {"UserDefinedFunctions": []}


def _get_user_defined_function(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    glue_repo.get_database(conn, params.get("DatabaseName"))
    raise glue_repo.GlueEntityNotFound("function_not_found", "Function not found.")


def _create_user_defined_function(_conn: sqlite3.Connection, _params: dict[str, Any]) -> dict[str, Any]:
    raise GlueInvalidInput("udf_not_supported", "User-defined functions are not supported by this catalog.")


READ_OPERATIONS: dict[str, Operation] = {
    "GetDatabase": _get_database,
    "GetDatabases": _get_databases,
    "GetTable": _get_table,
    "GetTables": _get_tables,
    "GetPartitions": _get_partitions,
    "GetPartition": _get_partition,
    "GetUserDefinedFunctions": _get_user_defined_functions,
    "GetUserDefinedFunction": _get_user_defined_function,
}
WRITE_OPERATIONS: dict[str, Operation] = {
    "CreateDatabase": _create_database,
    "UpdateDatabase": _update_database,
    "DeleteDatabase": _delete_database,
    "CreateTable": _create_table,
    "UpdateTable": _update_table,
    "DeleteTable": _delete_table,
    "CreatePartition": _create_partition,
    "BatchCreatePartition": _batch_create_partition,
    "BatchDeletePartition": _batch_delete_partition,
    "DeletePartition": _delete_partition,
    "UpdatePartition": _update_partition,
    "CreateUserDefinedFunction": _create_user_defined_function,
}
