"""Catálogo persistente (`<home>/catalog.db`): databases e tabelas, sem SparkSession nem kernel."""

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..catalog import glue_repo, glue_view, iceberg_jdbc, registry, schemas, tables
from ..catalog.catalog_info import KNOWN_CATALOGS, build_catalog_info
from ..catalog.store import catalog_db_path, connect
from ..kernels.service import KernelsBusy
from ..notislake import objectstore
from ..security import require_token, require_trusted_host
from .deps import Kernels

# Token is checked first (401), then Host (403).
router = APIRouter(prefix="/api/catalog", dependencies=[Depends(require_token), Depends(require_trusted_host)])

NAME_MAX = 256

# Referências fortes às exclusões em andamento (o event loop só guarda referência fraca).
_delete_tasks: set[asyncio.Task[dict[str, Any]]] = set()


def _delete_done(task: asyncio.Task[dict[str, Any]]) -> None:
    _delete_tasks.discard(task)
    if not task.cancelled():
        task.exception()  # consome o erro de uma tarefa órfã (handler já cancelado)


Name = Annotated[str, Query(min_length=1, max_length=NAME_MAX)]


def _get_home(request: Request) -> Path:
    home: Path = request.app.state.settings.home
    return home


Home = Annotated[Path, Depends(_get_home)]


def _open(home: Path) -> sqlite3.Connection | None:
    """Conexão só de leitura; `None` se o db ainda não existe (consultar não cria arquivo)."""
    if not catalog_db_path(home).exists():
        return None
    conn = connect(home)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _read_catalogs(home: Path) -> list[dict[str, Any]]:
    conn = _open(home)
    if conn is None:
        return [
            {"name": registry.SPARK_CATALOG, "databases": [{"name": ns, "tables": []} for ns in registry.empty_display_names()]},
            {"name": glue_view.GLUE_CATALOG, "databases": glue_view.empty_databases()},
        ]
    try:
        databases, used = registry.list_databases(conn, registry.MAX_TOTAL_TABLES)
        spark_node: dict[str, Any] = {"name": registry.SPARK_CATALOG, "databases": databases}
        try:
            ice_dbs, _ = iceberg_jdbc.list_databases(conn, registry.MAX_TOTAL_TABLES - used)
            iceberg_node: dict[str, Any] = {"name": iceberg_jdbc.ICEBERG_CATALOG, "databases": ice_dbs}
        except iceberg_jdbc.UnsupportedIcebergSchema:
            iceberg_node = iceberg_jdbc.error_entry(iceberg_jdbc.ERR_UNSUPPORTED)
        except sqlite3.Error:
            iceberg_node = iceberg_jdbc.error_entry(iceberg_jdbc.ERR_UNREADABLE)
        return [spark_node, iceberg_node, _glue_node(conn, registry.MAX_TOTAL_TABLES - used)]
    finally:
        conn.close()


def _glue_node(conn: sqlite3.Connection, remaining: int) -> dict[str, Any]:
    """Nó `glue`; falha de leitura degrada só este nó (como o Iceberg), sem derrubar a árvore."""
    try:
        databases, _ = glue_view.list_databases(conn, remaining)
    except sqlite3.Error:
        return glue_view.error_entry()
    return {"name": glue_view.GLUE_CATALOG, "databases": databases}


def _store_opener(request: Request) -> iceberg_jdbc.StoreOpener:
    """Resolve a conexão do bucket só quando a tabela Iceberg está em `s3a` (o metadata é lido do bucket)."""
    home = _get_home(request)
    supervisor = getattr(request.app.state, "notislake", None)
    return lambda: objectstore.resolve_from_app(home, supervisor)


def _dispatch[T](
    home: Path,
    catalog: str,
    *,
    spark: Callable[[sqlite3.Connection], T],
    iceberg: Callable[[sqlite3.Connection], T],
    glue: Callable[[sqlite3.Connection], T],
) -> T | None:
    """Abre o catálogo só leitura e delega ao leitor do `catalog`; `None` se o db não existe ou o catálogo é desconhecido."""
    conn = _open(home)
    if conn is None:
        return None
    try:
        if catalog == registry.SPARK_CATALOG:
            return spark(conn)
        if catalog == iceberg_jdbc.ICEBERG_CATALOG:
            return iceberg(conn)
        if catalog == glue_view.GLUE_CATALOG:
            return glue(conn)
        return None
    finally:
        conn.close()


def _read_table_info(
    home: Path, catalog: str, database: str, table: str, open_store: iceberg_jdbc.StoreOpener
) -> dict[str, Any] | None:
    return _dispatch(
        home,
        catalog,
        spark=lambda conn: registry.read_table_info(conn, database, table),
        iceberg=lambda conn: iceberg_jdbc.read_table_info(conn, database, table, open_store),
        glue=lambda conn: glue_view.read_table_info(conn, database, table),
    )


@router.get("")
async def get_catalog(home: Home) -> dict[str, Any]:
    try:
        catalogs = await asyncio.to_thread(_read_catalogs, home)
    except sqlite3.Error as exc:
        raise HTTPException(503, "Catalog database unavailable") from exc
    return {"status": "ok", "catalogs": catalogs}


@router.get("/table")
async def get_table_info(request: Request, home: Home, catalog: Name, database: Name, table: Name) -> dict[str, Any]:
    """Metadados de uma tabela, só leitura. 404 se inexistente, 409 se o schema JDBC Iceberg não for suportado, 503 se o db falhar.

    Falha só no `metadata.json` do Iceberg devolve 200 com `metadata_error` e os campos do registro.
    """
    try:
        info = await asyncio.to_thread(_read_table_info, home, catalog, database, table, _store_opener(request))
    except iceberg_jdbc.UnsupportedIcebergSchema as exc:
        raise HTTPException(409, iceberg_jdbc.ERR_UNSUPPORTED) from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "Catalog database unavailable") from exc
    if info is None:
        raise HTTPException(404, "Table not found")
    return info


def _read_catalog_info(home: Path, catalog: str) -> dict[str, Any]:
    conn = _open(home)
    try:
        if catalog == glue_view.GLUE_CATALOG:
            return glue_view.build_catalog_info(conn)
        return build_catalog_info(home, catalog, conn)
    finally:
        if conn is not None:
            conn.close()


@router.get("/info")
async def get_catalog_info(home: Home, catalog: Name) -> dict[str, Any]:
    """Visão geral de um catálogo (`spark_catalog`, `iceberg` ou `glue`), só leitura. 404 desconhecido, 503 se o db falhar.

    Sem `catalog.db` devolve `status: "empty"`; Iceberg ilegível devolve 200 com o status degradado. Segredos saem mascarados.
    """
    if catalog not in (*KNOWN_CATALOGS, glue_view.GLUE_CATALOG):
        raise HTTPException(404, "Catalog not found")
    try:
        return await asyncio.to_thread(_read_catalog_info, home, catalog)
    except sqlite3.Error as exc:
        raise HTTPException(503, "Catalog database unavailable") from exc


class CreateSchemaBody(BaseModel):
    catalog: str
    name: str


def _sqlite_http(exc: sqlite3.Error) -> HTTPException:
    """Lock ocupado (outro escritor) é transitório: 503 `catalog_busy`; o resto, `catalog_unavailable`."""
    text = str(exc).lower()
    return HTTPException(503, "catalog_busy" if "locked" in text or "busy" in text else "catalog_unavailable")


def _glue_schema_http(exc: glue_repo.GlueError) -> HTTPException:
    """Erro do `glue_repo` no vocabulário de `SchemaError`; `protected_database` é o `default`."""
    if isinstance(exc, glue_repo.GlueEntityNotFound):
        return HTTPException(404, "schema_not_found")
    if isinstance(exc, glue_repo.GlueAlreadyExists):
        return HTTPException(409, "schema_exists")
    if exc.reason == "protected_database":
        return HTTPException(409, "cannot_drop_default")
    return HTTPException(400, exc.reason)


async def _run_schema_op(fn: Any, *args: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args)
    except schemas.SchemaError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    except glue_repo.GlueError as exc:
        raise _glue_schema_http(exc) from exc
    except sqlite3.Error as exc:
        raise _sqlite_http(exc) from exc


@router.post("/schemas", status_code=201)
async def create_schema(body: CreateSchemaBody, home: Home) -> dict[str, str]:
    """Cria um schema sem SparkSession. 400 nome/catálogo inválido, 409 já existe, 503 db ocupado/indisponível."""
    result: dict[str, str] = await _run_schema_op(schemas.create_schema, home, body.catalog, body.name)
    return result


@router.get("/schemas/preview")
async def preview_schema(home: Home, catalog: Name, schema: Name) -> dict[str, Any]:
    """O que a exclusão do schema removeria, com o `etag` que o DELETE exige."""
    result: dict[str, Any] = await _run_schema_op(schemas.preview_schema, home, catalog, schema)
    return result


async def _with_idle_kernels(kernels: Kernels, op: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    """Roda `op` com os kernels reservados (células novas são abortadas); 409 `kernel_busy` se há célula rodando.

    A tarefa dona da reserva sobrevive ao cancelamento do handler (a thread da operação não é interrompível).
    """

    async def reserved() -> dict[str, Any]:
        with kernels.reserve_idle():
            return await op()

    task = asyncio.create_task(reserved())
    _delete_tasks.add(task)
    task.add_done_callback(_delete_done)
    try:
        return await asyncio.shield(task)
    except KernelsBusy as exc:
        raise HTTPException(409, "kernel_busy") from exc


@router.delete("/schemas")
async def delete_schema(home: Home, kernels: Kernels, catalog: Name, schema: Name, etag: Name) -> dict[str, Any]:
    """Exclui o schema em cascata (linhas no catálogo e pastas MANAGED). 409 `kernel_busy` se há célula rodando.

    Os kernels ficam reservados (células novas são abortadas) até o fim da exclusão, mesmo que o
    cliente desconecte e o handler seja cancelado.
    """
    try:
        schemas.validate(catalog, schema)
    except schemas.SchemaError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    if catalog == registry.SPARK_CATALOG and schema.lower() == registry.DEFAULT_DATABASE:
        raise HTTPException(409, "cannot_drop_default")
    if catalog == glue_view.GLUE_CATALOG and schema.lower() == registry.DEFAULT_DATABASE:
        raise HTTPException(409, "cannot_drop_default")

    return await _with_idle_kernels(kernels, lambda: _run_schema_op(schemas.delete_schema, home, catalog, schema, etag))


async def _run_table_op(fn: Any, *args: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args)
    except tables.TableError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    except sqlite3.Error as exc:
        raise _sqlite_http(exc) from exc


@router.get("/tables/preview")
async def preview_table(home: Home, catalog: Name, database: Name, table: Name) -> dict[str, Any]:
    """Efeito da remoção da tabela do catálogo (`spark_catalog`, `glue` ou `iceberg`) e o `etag` que o DELETE exige.

    400 catálogo/nome inválido, 404 inexistente, 409 schema JDBC Iceberg não suportado, 503 db ocupado/indisponível.
    """
    result: dict[str, Any] = await _run_table_op(tables.preview_table, home, catalog, database, table)
    return result


@router.delete("/tables")
async def remove_table(home: Home, kernels: Kernels, catalog: Name, database: Name, table: Name, etag: Name) -> dict[str, Any]:
    """Remove a linha da tabela do catálogo; própria gerenciada com pasta livre enfileira a pasta (o backend nunca apaga).

    400 catálogo/nome inválido, 404 inexistente, 409 `catalog_changed` (etag obsoleto), `kernel_busy` (só `glue` e
    `iceberg`, que exigem kernels ociosos) ou schema JDBC Iceberg não suportado, 503 db ocupado/indisponível.
    O `spark_catalog` não reserva kernels: as sessões abertas convergem pela `generation`.
    """
    try:
        tables.validate(catalog, database, table)
    except tables.TableError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    if catalog == registry.SPARK_CATALOG:
        result: dict[str, Any] = await _run_table_op(tables.remove_table, home, catalog, database, table, etag)
        return result

    return await _with_idle_kernels(kernels, lambda: _run_table_op(tables.remove_table, home, catalog, database, table, etag))
