"""API `/api/notislake`: estado do MinIO local, configuração S3 manual, listagem do bucket e teste de conexão.

O segredo da config manual nunca sai daqui (só `has_secret`); a única exceção deliberada é
`GET /local/credentials`, que devolve a credencial do MinIO local sob demanda para cópia. Nenhuma
resposta ecoa valor de entrada. Falha do destino S3 vira 502/504/400, nunca 401/403: o frontend trata 401 como sessão inválida.
"""

import re
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from ..config import Settings
from ..notislake import objectstore, settings_store
from ..notislake.bootstrap import BUCKET
from ..notislake.objectstore import Connection, ObjectStoreError, Unavailable
from ..notislake.ports import LOOPBACK
from ..notislake.settings_store import ConfigInvalid, ManualConfig
from ..notislake.supervisor import NotislakeSupervisor
from ..security import require_token, require_trusted_host

NO_STORE = {"Cache-Control": "no-store"}
MAX_PREFIX_LENGTH = 1024
MAX_TOKEN_LENGTH = 2048
DEFAULT_REGION = "us-east-1"
DEFAULT_TIMEOUT_S = 10
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\\]")

# Códigos do destino S3 que não são 502: timeout é 504 e token inválido é erro do cliente.
_STATUS_BY_CODE = {objectstore.TIMEOUT: 504, objectstore.INVALID_TOKEN: 400}
_test_lock = threading.Lock()


class _NoStoreRoute(APIRoute):
    """Põe `Cache-Control: no-store` também nas respostas de erro (401/403/422/4xx) das rotas do router."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except HTTPException as exc:
                raise HTTPException(exc.status_code, exc.detail, headers={**(exc.headers or {}), **NO_STORE}) from None
            except RequestValidationError as exc:
                # Sem `input`: o corpo pode conter o segredo e o handler padrão o devolveria.
                errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
                return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422, headers=NO_STORE)
            response.headers.update(NO_STORE)
            return response

        return handler


# Token primeiro (401), depois Host (403).
router = APIRouter(
    prefix="/api/notislake",
    dependencies=[Depends(require_token), Depends(require_trusted_host)],
    route_class=_NoStoreRoute,
)


class _NoSupervisor:
    """Substituto quando o app sobe sem supervisor (ex.: harness): nunca há MinIO local."""

    def connection(self) -> None:
        return None


class ConfigBody(BaseModel):
    """Rascunho da conexão manual. Campos `Any`: a validação de tipo e valor é do `settings_store`."""

    name: Any = None
    endpoint: Any = None
    access_key: Any = None
    secret_key: Any = None
    region: Any = DEFAULT_REGION
    timeout_s: Any = DEFAULT_TIMEOUT_S


def _supervisor(request: Request) -> NotislakeSupervisor | None:
    return request.app.state.notislake


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _home(request: Request) -> Path:
    return _settings(request).home


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message})


def _field_error(exc: ConfigInvalid, location: str = "body") -> HTTPException:
    loc = [location, exc.field] if exc.field else [location]
    return HTTPException(422, detail=[{"loc": loc, "msg": str(exc), "type": "value_error"}])


def _load_current(home: Path) -> ManualConfig | None:
    """Config manual vigente para reaproveitar o segredo; inválida ou ausente → `None`."""
    try:
        return settings_store.load(home)
    except ConfigInvalid:
        return None


def _manual_view(config: ManualConfig) -> dict[str, Any]:
    return {
        "mode": "manual",
        "name": config.name,
        "endpoint": config.endpoint,
        "access_key": config.access_key,
        "region": config.region,
        "timeout_s": config.timeout_s,
        "has_secret": config.has_secret,
    }


def _mode(home: Path) -> str:
    try:
        return "automatic" if settings_store.load(home) is None else "manual"
    except ConfigInvalid:
        return "invalid"


def _config_invalid() -> HTTPException:
    return _error(409, "config_invalid", "A configuração manual do notislake está inválida; corrija ou remova-a.")


def _upstream(exc: ObjectStoreError) -> HTTPException:
    status_code = _STATUS_BY_CODE.get(exc.code, 502)
    if exc.code == objectstore.INVALID_TOKEN:
        code = exc.code
    elif exc.code == objectstore.UPSTREAM_ERROR:
        code = "upstream_error"
    else:
        code = f"upstream_{exc.code}"
    return _error(status_code, code, str(exc))


def _resolve(request: Request) -> Connection:
    supervisor: Any = _supervisor(request) or _NoSupervisor()
    try:
        return objectstore.resolve(_home(request), supervisor)
    except ConfigInvalid:
        raise _config_invalid() from None
    except Unavailable:
        raise _error(503, "notislake_unavailable", "O MinIO local não está em execução.") from None


def _draft_connection(request: Request, body: ConfigBody) -> tuple[ManualConfig, Connection]:
    home = _home(request)
    try:
        config = settings_store.validate(
            name=body.name if body.name is not None else "teste",
            endpoint=body.endpoint,
            access_key=body.access_key,
            secret_key=body.secret_key,
            region=body.region,
            timeout_s=body.timeout_s,
            backend_port=_settings(request).port,
            current=_load_current(home),
        )
    except ConfigInvalid as exc:
        raise _draft_error(exc, body) from None
    connection = Connection(
        source="manual",
        endpoint=config.endpoint,
        access_key=config.access_key,
        secret_key=config.secret_key,
        region=config.region,
        connect_timeout_s=float(config.timeout_s),
        read_timeout_s=float(config.timeout_s),
    )
    return config, connection


def _draft_error(exc: ConfigInvalid, body: ConfigBody) -> HTTPException:
    if exc.field == "secret_key" and body.secret_key in (None, ""):
        return _error(422, "secret_required", "Informe o segredo: o endpoint ou a access_key mudou.")
    return _field_error(exc)


def _local_view(request: Request) -> dict[str, Any] | None:
    supervisor = _supervisor(request)
    if supervisor is None:
        return None
    snap = supervisor.snapshot()
    return {
        "state": snap.state.value,
        "since": snap.since.isoformat(),
        "restarts": snap.restarts,
        "api_port": snap.api_port,
        "console_port": snap.console_port,
        "console_url": f"http://{LOOPBACK}:{snap.console_port}" if snap.console_port else None,
        "error": {"code": snap.error.code, "message": snap.error.message} if snap.error else None,
    }


@router.get("/status")
def get_status(request: Request) -> dict[str, Any]:
    return {"mode": _mode(_home(request)), "local": _local_view(request)}


@router.post("/retry", status_code=202)
def retry(request: Request) -> dict[str, Any]:
    supervisor = _supervisor(request)
    if supervisor is None or not supervisor.retry():
        raise _error(409, "not_failed", "O MinIO local só pode ser retomado quando está em falha.")
    return {"state": supervisor.snapshot().state.value}


@router.get("/local/credentials")
def get_local_credentials(request: Request) -> dict[str, str]:
    supervisor = _supervisor(request)
    connection = supervisor.connection() if supervisor is not None else None
    if connection is None:
        raise _error(409, "not_running", "O MinIO local não está em execução.")
    return {"user": connection.access_key, "password": connection.secret_key}


@router.get("/config")
def get_config(request: Request) -> dict[str, Any]:
    try:
        config = settings_store.load(_home(request))
    except ConfigInvalid as exc:
        return {"mode": "invalid", "field": exc.field}
    if config is not None:
        return _manual_view(config)
    supervisor = _supervisor(request)
    connection = supervisor.connection() if supervisor is not None else None
    if connection is None:
        return {"mode": "automatic", "local": None}
    local = {"endpoint": connection.endpoint, "access_key": connection.access_key, "region": DEFAULT_REGION}
    return {"mode": "automatic", "local": local}


@router.put("/config")
def put_config(request: Request, body: ConfigBody) -> dict[str, Any]:
    if body.name is None:
        raise _field_error(ConfigInvalid("name is required", "name"))
    config, _ = _draft_connection(request, body)
    settings_store.save(_home(request), config)
    return _manual_view(config)


@router.delete("/config", status_code=204)
def delete_config(request: Request) -> Response:
    settings_store.clear(_home(request))
    return Response(status_code=204)


def _check_prefix(prefix: str) -> str:
    if (
        len(prefix) > MAX_PREFIX_LENGTH
        or prefix.startswith("/")
        or _CONTROL_RE.search(prefix)
        or any(part in (".", "..") for part in prefix.split("/"))
    ):
        raise HTTPException(422, detail=[{"loc": ["query", "prefix"], "msg": "prefix is invalid", "type": "value_error"}])
    return prefix


@router.get("/objects")
def list_objects(
    request: Request,
    prefix: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)] = "",
    max_keys: Annotated[int, Query(ge=1, le=1000)] = 100,
    continuation_token: Annotated[str | None, Query(max_length=MAX_TOKEN_LENGTH)] = None,
) -> dict[str, Any]:
    _check_prefix(prefix)
    connection = _resolve(request)
    try:
        page = objectstore.list_page(connection, prefix, max_keys, continuation_token)
    except ObjectStoreError as exc:
        raise _upstream(exc) from None
    return {
        "source": connection.source,
        "bucket": BUCKET,
        "prefix": prefix,
        "prefixes": page.prefixes,
        "objects": [
            {
                "key": item.key,
                "size": item.size,
                "last_modified": item.last_modified.isoformat() if item.last_modified else None,
            }
            for item in page.objects
        ],
        "is_truncated": page.is_truncated,
        "next_continuation_token": page.next_continuation_token,
    }


@router.post("/test")
def test_connection(request: Request, body: ConfigBody | None = None) -> dict[str, Any]:
    """Sonda o destino do rascunho (ou a conexão vigente, sem corpo); só devolve resultado categórico."""
    if not _test_lock.acquire(blocking=False):
        raise _error(409, "test_in_progress", "Já existe um teste de conexão em andamento.")
    try:
        connection = _resolve(request) if body is None else _draft_connection(request, body)[1]
        try:
            objectstore.probe(connection)
        except ObjectStoreError as exc:
            return {"ok": False, "source": connection.source, "code": exc.code, "message": str(exc)}
        return {"ok": True, "source": connection.source}
    finally:
        _test_lock.release()

