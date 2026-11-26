"""API `/api/notislake`: estado do MinIO local, configuração S3 manual, buckets, listagem e teste de conexão.

O segredo da config manual nunca sai daqui (só `has_secret`); a única exceção deliberada é
`GET /local/credentials`, que devolve a credencial do MinIO local sob demanda para cópia. Nenhuma
resposta ecoa valor de entrada. Falha do destino S3 vira 502/504/400, nunca 401/403: o frontend trata 401 como sessão inválida.
"""

import logging
import re
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi import Path as PathParam
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from ..config import Settings
from ..notislake import objectstore, settings_store
from ..notislake.bootstrap import BUCKET, PREFIXES
from ..notislake.objectstore import Connection, ObjectStoreError, Unavailable
from ..notislake.locations import valid_bucket_name
from ..notislake.ports import LOOPBACK
from ..notislake.settings_store import ConfigInvalid, ManualConfig
from ..notislake.supervisor import LocalConnection, NotislakeSupervisor
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
# Um processo, um usuário local: exclusões em lote não concorrem entre si.
_delete_lock = threading.Lock()
logger = logging.getLogger(__name__)
_ROOT_ORDER = {prefix: index for index, prefix in enumerate(PREFIXES)}


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


def _local_connection(request: Request) -> LocalConnection | None:
    supervisor = _supervisor(request)
    return supervisor.connection() if supervisor is not None else None


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
    connection = _local_connection(request)
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
    connection = _local_connection(request)
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


def _bad_input(location: str, name: str, msg: str) -> HTTPException:
    return HTTPException(422, detail=[{"loc": [location, name], "msg": msg, "type": "value_error"}])


def _check_bucket(bucket: str, location: str = "query", field: str = "bucket") -> str:
    if not valid_bucket_name(bucket):
        raise _bad_input(location, field, "bucket name is invalid")
    return bucket


def _check_folder(prefix: str, *, allow_empty: bool) -> str:
    """Prefixo de pasta: vazio só quando permitido; senão termina em `/` (`bronze/` nunca alcança `bronze2/`)."""
    _check_prefix(prefix)
    if (not prefix and not allow_empty) or (prefix and not prefix.endswith("/")):
        raise _bad_input("query", "prefix", "prefix is invalid")
    return prefix


def _check_key(key: str) -> str:
    """Chave de um arquivo: não vazia e sem `/` final (pasta se exclui por `/folders`); `a//b.csv` é válida."""
    try:
        _check_prefix(key)
    except HTTPException:
        raise _bad_input("query", "key", "key is invalid") from None
    if not key or key.endswith("/"):
        raise _bad_input("query", "key", "key is invalid")
    return key


def _bucket_upstream(exc: ObjectStoreError) -> HTTPException:
    """Como `_upstream`, mas bucket inexistente é 404: nas rotas por bucket o alvo é do cliente."""
    if exc.code == objectstore.BUCKET_MISSING:
        return _error(404, "bucket_missing", str(exc))
    return _upstream(exc)


def _local_connection_for_write(request: Request) -> Connection:
    """Conexão do MinIO local; modo manual (S3 externo) não cria nem exclui."""
    connection = _resolve(request)
    if connection.source == "manual":
        raise _error(409, "manual_mode_unsupported", "Criar e excluir só é possível no MinIO local.")
    return connection


def _content_changed(current: int) -> HTTPException:
    detail = {
        "code": "content_changed",
        "message": "O conteúdo mudou desde a confirmação; revise e confirme de novo.",
        "object_count": current,
    }
    return HTTPException(409, detail=detail)


def _acquire_delete() -> None:
    if not _delete_lock.acquire(blocking=False):
        raise _error(409, "delete_in_progress", "Já existe uma exclusão em andamento.")


def _root_sorted(prefixes: list[str]) -> list[str]:
    """Raiz do bucket: landing, bronze, silver, gold (os que existirem) e depois as demais em ordem alfabética."""
    return sorted(prefixes, key=lambda item: (_ROOT_ORDER.get(item, len(_ROOT_ORDER)), item))


@router.get("/buckets")
def list_buckets(request: Request) -> dict[str, Any]:
    try:
        manual = settings_store.load(_home(request)) is not None
    except ConfigInvalid:
        raise _config_invalid() from None
    if manual:
        # No S3 externo o IAM pode negar `ListBuckets`; a lista é sintética (só o bucket configurado).
        return {"source": "manual", "buckets": [BUCKET]}
    connection = _resolve(request)
    try:
        names = objectstore.list_buckets(connection)
    except ObjectStoreError as exc:
        raise _upstream(exc) from None
    return {"source": connection.source, "buckets": names}


class BucketBody(BaseModel):
    name: str


@router.post("/buckets", status_code=201)
def create_bucket(request: Request, body: BucketBody) -> dict[str, str]:
    name = _check_bucket(body.name, "body", "name")
    connection = _local_connection_for_write(request)
    try:
        objectstore.create_bucket_with_folders(connection, name)
    except ObjectStoreError as exc:
        if exc.code == objectstore.BUCKET_EXISTS:
            raise _error(409, "bucket_exists", str(exc)) from None
        raise _upstream(exc) from None
    return {"name": name}


@router.get("/objects")
def list_objects(
    request: Request,
    prefix: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)] = "",
    max_keys: Annotated[int, Query(ge=1, le=1000)] = 100,
    continuation_token: Annotated[str | None, Query(max_length=MAX_TOKEN_LENGTH)] = None,
    bucket: Annotated[str | None, Query(max_length=MAX_PREFIX_LENGTH)] = None,
) -> dict[str, Any]:
    _check_prefix(prefix)
    if bucket is not None:
        _check_bucket(bucket)
    connection = _resolve(request)
    if bucket is not None and connection.source == "manual" and bucket != BUCKET:
        raise _error(409, "manual_mode_unsupported", "No S3 externo só o bucket configurado é acessível.")
    try:
        if bucket is None:
            page = objectstore.list_page(connection, prefix, max_keys, continuation_token)
        else:
            page = objectstore.list_page(connection, prefix, max_keys, continuation_token, bucket=bucket)
    except ObjectStoreError as exc:
        raise (_upstream(exc) if bucket is None else _bucket_upstream(exc)) from None
    prefixes = page.prefixes if bucket is None or prefix else _root_sorted(page.prefixes)
    return {
        "source": connection.source,
        "bucket": BUCKET if bucket is None else bucket,
        "prefix": prefix,
        "prefixes": prefixes,
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


@router.get("/buckets/{bucket}/summary")
def bucket_summary(
    request: Request,
    bucket: Annotated[str, PathParam(max_length=MAX_PREFIX_LENGTH)],
    prefix: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)] = "",
) -> dict[str, int]:
    _check_bucket(bucket, "path")
    _check_folder(prefix, allow_empty=True)
    connection = _local_connection_for_write(request)
    try:
        return {"object_count": objectstore.count_keys_under(connection, bucket, prefix)}
    except ObjectStoreError as exc:
        raise _bucket_upstream(exc) from None


def _delete_listed(connection: Connection, bucket: str, prefix: str, expected_count: int) -> int:
    """Conta por página, confere com a contagem confirmada e só então apaga página por página.

    Contagem atual maior ⇒ 409 `content_changed` sem apagar nada. Há uma janela entre a contagem e a
    exclusão: objetos criados nela também são apagados (a segunda listagem é a que vale); `_delete_lock`
    só serializa exclusões deste processo, não escritas externas. Memória limitada a uma página.
    """
    current = objectstore.count_keys_under(connection, bucket, prefix)
    if current > expected_count:
        raise _content_changed(current)
    removed = 0
    for page in objectstore.iter_key_pages(connection, bucket, prefix):
        removed += objectstore.delete_keys(connection, bucket, page)
    return removed


@router.delete("/buckets/{bucket}")
def delete_bucket(
    request: Request,
    bucket: Annotated[str, PathParam(max_length=MAX_PREFIX_LENGTH)],
    expected_count: Annotated[int, Query(ge=0)],
) -> dict[str, int]:
    _check_bucket(bucket, "path")
    _acquire_delete()
    try:
        connection = _local_connection_for_write(request)
        try:
            removed = _delete_listed(connection, bucket, "", expected_count)
            objectstore.delete_bucket(connection, bucket)
        except ObjectStoreError as exc:
            if exc.code == objectstore.BUCKET_NOT_EMPTY:
                raise _error(409, "bucket_not_empty", str(exc)) from None
            raise _bucket_upstream(exc) from None
        logger.info("notislake: bucket excluído com %d objetos", removed)
        return {"deleted": removed}
    finally:
        _delete_lock.release()


@router.delete("/folders")
def delete_folder(
    request: Request,
    bucket: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)],
    prefix: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)],
    expected_count: Annotated[int, Query(ge=0)],
) -> dict[str, int]:
    _check_bucket(bucket)
    _check_folder(prefix, allow_empty=False)
    _acquire_delete()
    try:
        connection = _local_connection_for_write(request)
        try:
            removed = _delete_listed(connection, bucket, prefix, expected_count)
        except ObjectStoreError as exc:
            raise _bucket_upstream(exc) from None
        logger.info("notislake: pasta excluída com %d objetos", removed)
        return {"deleted": removed}
    finally:
        _delete_lock.release()


def _object_exists(connection: Connection, bucket: str, key: str) -> bool:
    """Existência via `get_bounded(max_bytes=0)`: `TOO_LARGE` prova que o objeto existe, sem ler o corpo."""
    try:
        objectstore.get_bounded(connection, key, max_bytes=0, bucket=bucket)
    except ObjectStoreError as exc:
        if exc.code == objectstore.TOO_LARGE:
            return True
        if exc.code == objectstore.OBJECT_MISSING:
            return False
        raise
    return True


@router.delete("/objects")
def delete_object(
    request: Request,
    bucket: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)],
    key: Annotated[str, Query(max_length=MAX_PREFIX_LENGTH)],
) -> dict[str, int]:
    _check_bucket(bucket)
    _check_key(key)
    _acquire_delete()
    try:
        connection = _local_connection_for_write(request)
        try:
            # `DeleteObject` é idempotente e não diz se o objeto existia; a rota confere antes.
            if not _object_exists(connection, bucket, key):
                return {"deleted": 0}
            objectstore.delete_key(connection, key, bucket=bucket)
        except ObjectStoreError as exc:
            raise _bucket_upstream(exc) from None
        return {"deleted": 1}
    finally:
        _delete_lock.release()


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

