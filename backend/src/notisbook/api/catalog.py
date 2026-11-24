"""Catálogo persistente (`<home>/catalog.db`): databases e tabelas, sem SparkSession nem kernel."""

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..catalog import iceberg_jdbc, registry, schemas
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
            {"name": node, "databases": [{"name": ns, "tables": []} for ns in registry.empty_display_names()]}
            for node in (registry.SPARK_CATALOG, registry.HUDI_CATALOG)
        ]
    try:
        databases, used = registry.list_databases(conn, registry.MAX_TOTAL_TABLES)
        hudi_dbs, hudi_used = registry.list_databases(conn, registry.MAX_TOTAL_TABLES - used, hudi=True)
        used += hudi_used
        spark_node: dict[str, Any] = {"name": registry.SPARK_CATALOG, "databases": databases}
        try:
            ice_dbs, _ = iceberg_jdbc.list_databases(conn, registry.MAX_TOTAL_TABLES - used)
            iceberg_node: dict[str, Any] = {"name": iceberg_jdbc.ICEBERG_CATALOG, "databases": ice_dbs}
        except iceberg_jdbc.UnsupportedIcebergSchema:
            iceberg_node = iceberg_jdbc.error_entry(iceberg_jdbc.ERR_UNSUPPORTED)
        except sqlite3.Error:
            iceberg_node = iceberg_jdbc.error_entry(iceberg_jdbc.ERR_UNREADABLE)
        hudi_node: dict[str, Any] = {"name": registry.HUDI_CATALOG, "databases": hudi_dbs}
        return [spark_node, iceberg_node, hudi_node]
    finally:
        conn.close()


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
    hudi: Callable[[sqlite3.Connection], T],
    iceberg: Callable[[sqlite3.Connection], T],
) -> T | None:
    """Abre o catálogo só leitura e delega ao leitor do `catalog`; `None` se o db não existe ou o catálogo é desconhecido."""
    conn = _open(home)
    if conn is None:
        return None
    try:
        if catalog == registry.SPARK_CATALOG:
            return spark(conn)
        if catalog == registry.HUDI_CATALOG:
            return hudi(conn)
        if catalog == iceberg_jdbc.ICEBERG_CATALOG:
            return iceberg(conn)
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
        hudi=lambda conn: registry.read_table_info(conn, database, table, hudi_only=True),
        iceberg=lambda conn: iceberg_jdbc.read_table_info(conn, database, table, open_store),
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
        return build_catalog_info(home, catalog, conn)
    finally:
        if conn is not None:
            conn.close()


@router.get("/info")
async def get_catalog_info(home: Home, catalog: Name) -> dict[str, Any]:
    """Visão geral de um catálogo (`spark_catalog`, `iceberg` ou `hudi`), só leitura. 404 desconhecido, 503 se o db falhar.

    Sem `catalog.db` devolve `status: "empty"`; Iceberg ilegível devolve 200 com o status degradado. Segredos saem mascarados.
    """
    if catalog not in KNOWN_CATALOGS:
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


async def _run_schema_op(fn: Any, *args: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args)
    except schemas.SchemaError as exc:
        raise HTTPException(exc.status, exc.code) from exc
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
    if catalog in (registry.SPARK_CATALOG, registry.HUDI_CATALOG) and schema.lower() == registry.DEFAULT_DATABASE:
        raise HTTPException(409, "cannot_drop_default")

    async def reserved_delete() -> dict[str, Any]:
        with kernels.reserve_idle():
            result: dict[str, Any] = await _run_schema_op(schemas.delete_schema, home, catalog, schema, etag)
        return result

    # A tarefa (dona da reserva) sobrevive ao cancelamento do handler; a thread da exclusão não é interrompível.
    task = asyncio.create_task(reserved_delete())
    _delete_tasks.add(task)
    task.add_done_callback(_delete_done)
    try:
        result = await asyncio.shield(task)
    except KernelsBusy as exc:
        raise HTTPException(409, "kernel_busy") from exc
    return result
