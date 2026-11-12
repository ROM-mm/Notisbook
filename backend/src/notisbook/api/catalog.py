"""Catálogo persistente (`<home>/catalog.db`): databases, tabelas e colunas, sem SparkSession nem kernel."""

import asyncio
import sqlite3
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..catalog import iceberg_jdbc, registry, schemas
from ..catalog.store import catalog_db_path, connect
from ..kernels.service import KernelsBusy
from ..security import require_token, require_trusted_host
from ..spark.bundles import WAREHOUSE_DIR
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
        return [{"name": registry.SPARK_CATALOG, "databases": [{"name": registry.DEFAULT_DATABASE, "tables": []}]}]
    try:
        databases, used = registry.list_databases(conn, registry.MAX_TOTAL_TABLES)
        hudi_dbs, hudi_used = registry.list_databases(conn, registry.MAX_TOTAL_TABLES - used, hudi=True)
        used += hudi_used
        spark_node: dict[str, Any] = {"name": registry.SPARK_CATALOG, "databases": databases}
        warehouse = home / WAREHOUSE_DIR / "iceberg"
        try:
            ice_dbs, _ = iceberg_jdbc.list_databases(conn, warehouse, registry.MAX_TOTAL_TABLES - used)
            iceberg_node: dict[str, Any] = {"name": iceberg_jdbc.ICEBERG_CATALOG, "databases": ice_dbs}
        except iceberg_jdbc.UnsupportedIcebergSchema:
            iceberg_node = iceberg_jdbc.error_entry(iceberg_jdbc.ERR_UNSUPPORTED)
        except sqlite3.Error:
            iceberg_node = iceberg_jdbc.error_entry(iceberg_jdbc.ERR_UNREADABLE)
        hudi_node: dict[str, Any] = {"name": registry.HUDI_CATALOG, "databases": hudi_dbs}
        return [spark_node, iceberg_node, hudi_node]
    finally:
        conn.close()


def _read_columns(home: Path, catalog: str, database: str, table: str) -> list[dict[str, Any]] | None:
    conn = _open(home)
    if conn is None:
        return None
    try:
        if catalog == registry.SPARK_CATALOG:
            return registry.read_columns(conn, database, table)
        if catalog == registry.HUDI_CATALOG:
            return registry.read_columns(conn, database, table, hudi_only=True)
        if catalog == iceberg_jdbc.ICEBERG_CATALOG:
            return iceberg_jdbc.read_columns(conn, database, table)
        return None
    finally:
        conn.close()


@router.get("")
async def get_catalog(home: Home) -> dict[str, Any]:
    try:
        catalogs = await asyncio.to_thread(_read_catalogs, home)
    except sqlite3.Error as exc:
        raise HTTPException(503, "Catalog database unavailable") from exc
    return {"status": "ok", "catalogs": catalogs}


@router.get("/columns")
async def get_columns(home: Home, catalog: Name, database: Name, table: Name) -> list[dict[str, Any]]:
    """Colunas de uma tabela; 404 se inexistente, 409 se o formato do catálogo ou do metadata não for legível."""
    try:
        columns = await asyncio.to_thread(_read_columns, home, catalog, database, table)
    except iceberg_jdbc.UnsupportedIcebergSchema as exc:
        raise HTTPException(409, iceberg_jdbc.ERR_UNSUPPORTED) from exc
    except iceberg_jdbc.IcebergMetadataError as exc:
        raise HTTPException(409, "Table metadata unavailable") from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "Catalog database unavailable") from exc
    if columns is None:
        raise HTTPException(404, "Table not found")
    return columns


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
