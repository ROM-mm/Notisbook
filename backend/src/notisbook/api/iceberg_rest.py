"""Iceberg REST catalog para o kernel Docker: o `SparkCatalog` do container lê o catálogo `iceberg` só por aqui.

Autenticação pelo token de runtime da sessão (o mesmo de `/api/runtime-catalog`, nunca o da UI) e regra de
Host de runtime. Todo erro sai como `ErrorModel` (`{"error": {message, type, code}}`), inclusive 401/403 de
autenticação. Recusa de operação é sempre 403 (409 faria o cliente repetir; 5xx viraria estado de commit
desconhecido). O servidor lê o `metadata.json` do `metadata_location` do SQLite, só dentro da raiz Iceberg.
"""

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..catalog import iceberg_jdbc
from ..catalog.store import catalog_db_path, connect
from ..security import RuntimeGrant, require_runtime_host, require_runtime_token

log = logging.getLogger(__name__)

NAMESPACE_SEPARATOR = "\x1f"
MAX_NAME_LENGTH = 255
READ_ENDPOINTS = (
    "GET /v1/{prefix}/namespaces",
    "GET /v1/{prefix}/namespaces/{namespace}",
    "HEAD /v1/{prefix}/namespaces/{namespace}",
    "GET /v1/{prefix}/namespaces/{namespace}/tables",
    "GET /v1/{prefix}/namespaces/{namespace}/tables/{table}",
    "HEAD /v1/{prefix}/namespaces/{namespace}/tables/{table}",
)
READ_ONLY_MESSAGE = (
    "O catálogo Iceberg do runtime Docker é somente leitura nesta versão do Notisbook; "
    "crie ou altere tabelas Iceberg pelo runtime local"
)


class IcebergError(Exception):
    """Erro de protocolo REST do Iceberg, devolvido como `ErrorModel`."""

    def __init__(self, status: int, error_type: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type
        self.message = message


def error_response(exc: IcebergError) -> JSONResponse:
    body = {"error": {"message": exc.message, "type": exc.error_type, "code": exc.status}}
    return JSONResponse(body, status_code=exc.status)


async def handle_error(_request: Request, exc: Exception) -> Response:
    assert isinstance(exc, IcebergError)
    return error_response(exc)


async def _authenticate(request: Request) -> RuntimeGrant:
    """Token (401) e depois Host (403), reaproveitando as dependências de runtime com o corpo `ErrorModel`."""
    try:
        grant = await require_runtime_token(request)
        await require_runtime_host(request)
    except HTTPException as exc:
        kind = "NotAuthorizedException" if exc.status_code == 401 else "ForbiddenException"
        message = "Não autorizado" if exc.status_code == 401 else "Host não permitido"
        raise IcebergError(exc.status_code, kind, message) from None
    return grant


Grant = Annotated[RuntimeGrant, Depends(_authenticate)]
router = APIRouter(prefix="/iceberg", dependencies=[Depends(_authenticate)])


def _no_such_namespace() -> IcebergError:
    return IcebergError(404, "NoSuchNamespaceException", "Namespace não encontrado")


def _no_such_table() -> IcebergError:
    return IcebergError(404, "NoSuchTableException", "Tabela não encontrada")


def parse_namespace(raw: str) -> str:
    """Namespace do protocolo (níveis separados por 0x1F) no formato pontuado do JdbcCatalog."""
    levels = raw.split(NAMESPACE_SEPARATOR)
    invalid = len(raw) > MAX_NAME_LENGTH or any(
        not level or "." in level or "\x00" in level for level in levels
    )
    if invalid:
        raise IcebergError(400, "BadRequestException", "Namespace inválido")
    return ".".join(levels)


def parse_table_name(raw: str) -> str:
    if not raw or len(raw) > MAX_NAME_LENGTH or "\x00" in raw:
        raise IcebergError(400, "BadRequestException", "Nome de tabela inválido")
    return raw


def _levels(namespace: str) -> list[str]:
    return namespace.split(".")


def _home(request: Request) -> Path:
    home: Path = request.app.state.settings.home
    return home


def _run_read[T](home: Path, func: Callable[[sqlite3.Connection, bool], T]) -> T:
    if not catalog_db_path(home).exists():
        raise IcebergError(503, "ServiceUnavailableException", "Catálogo ainda não inicializado")
    conn = connect(home)
    try:
        conn.execute("PRAGMA query_only=ON")
        try:
            has_type = iceberg_jdbc.check_schema(conn)
        except iceberg_jdbc.UnsupportedIcebergSchema:
            raise IcebergError(500, "ServiceFailureException", "Formato do catálogo Iceberg não suportado") from None
        return func(conn, has_type)
    finally:
        conn.close()


async def _read[T](request: Request, func: Callable[[sqlite3.Connection, bool], T]) -> T:
    try:
        return await asyncio.to_thread(_run_read, _home(request), func)
    except sqlite3.Error:
        raise IcebergError(503, "ServiceUnavailableException", "Catálogo ocupado ou indisponível") from None


def _require_namespace(conn: sqlite3.Connection, namespace: str) -> None:
    if not iceberg_jdbc.namespace_exists(conn, namespace):
        raise _no_such_namespace()


@router.get("/v1/config")
async def get_config() -> dict[str, Any]:
    """Sem `prefix`; `endpoints` explícito, porque o cliente trata a omissão como suporte a tudo."""
    return {"defaults": {}, "overrides": {}, "endpoints": list(READ_ENDPOINTS)}


@router.get("/v1/namespaces")
async def list_namespaces(request: Request, parent: str | None = None) -> dict[str, Any]:
    parent_ns = parse_namespace(parent) if parent else None

    def query(conn: sqlite3.Connection, _has_type: bool) -> list[str]:
        if parent_ns is not None:
            _require_namespace(conn, parent_ns)
        return iceberg_jdbc.list_child_namespaces(conn, parent_ns)

    names = await _read(request, query)
    return {"namespaces": [_levels(n) for n in names]}


@router.get("/v1/namespaces/{namespace}")
async def load_namespace(request: Request, namespace: str) -> dict[str, Any]:
    ns = parse_namespace(namespace)

    def query(conn: sqlite3.Connection, _has_type: bool) -> dict[str, str]:
        _require_namespace(conn, ns)
        return iceberg_jdbc.namespace_properties(conn, ns)

    return {"namespace": _levels(ns), "properties": await _read(request, query)}


@router.head("/v1/namespaces/{namespace}")
async def namespace_exists(request: Request, namespace: str) -> Response:
    ns = parse_namespace(namespace)

    def query(conn: sqlite3.Connection, _has_type: bool) -> None:
        _require_namespace(conn, ns)

    await _read(request, query)
    return Response(status_code=204)


@router.get("/v1/namespaces/{namespace}/tables")
async def list_tables(request: Request, namespace: str) -> dict[str, Any]:
    ns = parse_namespace(namespace)

    def query(conn: sqlite3.Connection, has_type: bool) -> list[str]:
        _require_namespace(conn, ns)
        return iceberg_jdbc.list_table_names(conn, ns, has_type)

    names = await _read(request, query)
    return {"identifiers": [{"namespace": _levels(ns), "name": name} for name in names]}


def _load_table(grant: RuntimeGrant, ns: str, table: str) -> Callable[[sqlite3.Connection, bool], dict[str, Any]]:
    def query(conn: sqlite3.Connection, has_type: bool) -> dict[str, Any]:
        location = iceberg_jdbc.table_metadata_location(conn, ns, table, has_type)
        if location is None:
            raise _no_such_table()
        try:
            metadata = iceberg_jdbc.read_metadata_within(location, grant.iceberg_root)
        except iceberg_jdbc.MetadataOutsideRoot:
            raise IcebergError(
                403, "ForbiddenException", "A tabela fica fora do warehouse Iceberg do Notisbook e não é acessível ao runtime Docker"
            ) from None
        except iceberg_jdbc.IcebergMetadataError:
            raise IcebergError(500, "ServiceFailureException", "Não foi possível ler o metadata da tabela") from None
        return {"metadata-location": location, "metadata": metadata, "config": {}}

    return query


@router.get("/v1/namespaces/{namespace}/tables/{table}")
async def load_table(request: Request, namespace: str, table: str, grant: Grant) -> dict[str, Any]:
    return await _read(request, _load_table(grant, parse_namespace(namespace), parse_table_name(table)))


@router.head("/v1/namespaces/{namespace}/tables/{table}")
async def table_exists(request: Request, namespace: str, table: str) -> Response:
    ns, name = parse_namespace(namespace), parse_table_name(table)

    def query(conn: sqlite3.Connection, has_type: bool) -> None:
        if iceberg_jdbc.table_metadata_location(conn, ns, name, has_type) is None:
            raise _no_such_table()

    await _read(request, query)
    return Response(status_code=204)


@router.post("/v1/namespaces/{namespace}/tables/{table}/metrics")
async def report_metrics(namespace: str, table: str) -> Response:
    """Relatório de métricas do cliente: aceito e descartado."""
    return Response(status_code=204)


def _read_only() -> IcebergError:
    return IcebergError(403, "ForbiddenException", READ_ONLY_MESSAGE)


@router.post("/v1/namespaces")
@router.delete("/v1/namespaces/{namespace}")
@router.post("/v1/namespaces/{namespace}/properties")
@router.post("/v1/namespaces/{namespace}/tables")
@router.post("/v1/namespaces/{namespace}/tables/{table}")
@router.delete("/v1/namespaces/{namespace}/tables/{table}")
@router.post("/v1/namespaces/{namespace}/register")
@router.post("/v1/tables/rename")
@router.post("/v1/transactions/commit")
async def refuse_write() -> Response:
    raise _read_only()


@router.api_route("/{rest:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"])
async def not_found() -> Response:
    raise IcebergError(404, "NoSuchRouteException", "Rota não encontrada")
