"""Endpoint compatível com o AWS Glue (AWS JSON 1.1) sobre o catálogo `glue` do `catalog.db`.

O GlueContext do runtime Glue fala com ele pelo `AWS_ENDPOINT_URL_GLUE`: `POST /glue` (boto3) ou `POST /glue/` (SDK Java
v2) com `X-Amz-Target: AWSGlue.<Operação>`. Autenticação SigV4 por sessão: access key = id da sessão, secret = token de
runtime dela (`RuntimeTokens.credentials`), mais a regra de Host de runtime do Iceberg REST. Falha de credencial responde
sempre igual (sessão desconhecida e assinatura inválida), sem indicar qual. Erros saem no formato AWS: HTTP 400,
`x-amzn-ErrorType` e `{"__type", "message"}`; falha interna é 500 `InternalServiceException`, que os SDKs repetem.
Nada de segredo, assinatura ou corpo vai para o log.
"""

import asyncio
import hmac
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..catalog import glue_ops, glue_repo, glue_sigv4
from ..catalog.store import catalog_db_path, ensure_catalog_db
from ..security import require_runtime_host

log = logging.getLogger(__name__)

MEDIA_TYPE = "application/x-amz-json-1.1"
TARGET_PREFIX = "AWSGlue."
MAX_BODY_BYTES = 8 * 1024 * 1024
BAD_CREDENTIALS = "The security token included in the request is invalid."

router = APIRouter()
# Segredo descartável por processo: a verificação de uma sessão desconhecida custa o mesmo que a de uma conhecida.
_UNKNOWN_SESSION_SECRET = secrets.token_urlsafe(32)
_ready_homes: set[Path] = set()

_ERROR_TYPES: tuple[tuple[type[glue_repo.GlueError], str], ...] = (
    (glue_repo.GlueEntityNotFound, "EntityNotFoundException"),
    (glue_repo.GlueAlreadyExists, "AlreadyExistsException"),
    (glue_repo.GlueInvalidInput, "InvalidInputException"),
    (glue_ops.ConcurrentModification, "ConcurrentModificationException"),
)


class AwsError(Exception):
    """Erro do protocolo, devolvido como `{"__type", "message"}` com `x-amzn-ErrorType`."""

    def __init__(self, status: int, error_type: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type
        self.message = message


def _error_response(exc: AwsError, request_id: str) -> JSONResponse:
    headers = {"x-amzn-ErrorType": exc.error_type, "x-amzn-RequestId": request_id}
    body = {"__type": exc.error_type, "message": exc.message}
    return JSONResponse(body, status_code=exc.status, media_type=MEDIA_TYPE, headers=headers)


def _domain_error(exc: glue_repo.GlueError) -> AwsError:
    for kind, name in _ERROR_TYPES:
        if isinstance(exc, kind):
            return AwsError(400, name, str(exc))
    return AwsError(500, "InternalServiceException", "Internal failure.")


def _home(request: Request) -> Path:
    home: Path = request.app.state.settings.home
    return home


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise AwsError(400, "InvalidInputException", "Request body is too large.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise AwsError(400, "InvalidInputException", "Request body is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _check_headers(request: Request) -> glue_sigv4.ParsedAuthorization:
    """Host e cabeçalhos de assinatura, antes de ler o corpo (requisição inválida não consome o corpo).

    Só a conferência do hash do corpo e da assinatura fica para `_verify_signature`."""
    try:
        await require_runtime_host(request)
    except HTTPException:
        raise AwsError(403, "AccessDeniedException", "Host not allowed.") from None
    try:
        auth = glue_sigv4.parse_authorization(request.headers.get("authorization"))
    except glue_sigv4.MalformedAuthorization:
        raise AwsError(403, "AccessDeniedException", "Missing or malformed authentication.") from None
    amz_date = request.headers.get("x-amz-date")
    if amz_date is None or not glue_sigv4.valid_amz_date(amz_date, auth):
        raise AwsError(403, "AccessDeniedException", "Missing or malformed authentication.")
    return auth


def _verify_signature(request: Request, body: bytes, auth: glue_sigv4.ParsedAuthorization) -> None:
    """SigV4 recalculado com o segredo da sessão; levanta `AwsError` (400 credencial/assinatura).

    Token de sessão que não é do runtime Glue recebe a mesma resposta de credencial inválida."""
    amz_date = request.headers["x-amz-date"]
    body_hash = glue_sigv4.payload_hash(body, request.headers.get("x-amz-content-sha256"))
    raw_path = request.scope.get("raw_path")
    path = raw_path.decode("latin-1") if isinstance(raw_path, bytes) else request.url.path
    canonical = glue_sigv4.canonical_request(
        request.method,
        path,
        request.url.query,
        request.headers.getlist,
        auth.signed_headers,
        body_hash or "",
    )
    entry = request.app.state.kernels.runtime_tokens.credentials(auth.access_key)
    expected = glue_sigv4.signature_for(entry[0] if entry else _UNKNOWN_SESSION_SECRET, amz_date, auth, canonical or "")
    matches = hmac.compare_digest(expected, auth.signature)
    is_glue = entry is not None and entry[1].glue
    if not (matches and is_glue and canonical is not None and body_hash is not None):
        raise AwsError(400, "UnrecognizedClientException", BAD_CREDENTIALS)


def _operation(request: Request) -> str:
    target = request.headers.get("x-amz-target", "")
    name = target[len(TARGET_PREFIX) :] if target.startswith(TARGET_PREFIX) else ""
    if name not in glue_ops.READ_OPERATIONS and name not in glue_ops.WRITE_OPERATIONS:
        raise AwsError(400, "UnknownOperationException", "The requested operation is not supported.")
    return name


def _reject_constant(_name: str) -> Any:
    raise ValueError("non-finite number")


def _params(request: Request, body: bytes) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != MEDIA_TYPE:
        raise AwsError(400, "SerializationException", f"Content-Type must be {MEDIA_TYPE}.")
    try:
        params = json.loads(body, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise AwsError(400, "SerializationException", "The request body is not valid JSON.") from None
    if not isinstance(params, dict):
        raise AwsError(400, "SerializationException", "The request body must be a JSON object.")
    return params


def _ensure_catalog(home: Path) -> None:
    """Cria/migra o `catalog.db` na primeira operação do processo (idempotente), para o `glue_*` existir."""
    if home in _ready_homes and catalog_db_path(home).exists():
        return
    ensure_catalog_db(home)
    _ready_homes.add(home)


def _execute(home: Path, name: str, params: dict[str, Any]) -> dict[str, Any]:
    _ensure_catalog(home)
    write = glue_ops.WRITE_OPERATIONS.get(name)
    if write is not None:
        with glue_repo.writer(home) as conn:
            return write(conn, params)
    with glue_repo.reader(home) as conn:
        if conn is None:
            raise glue_repo.GlueEntityNotFound("catalog_unavailable", "The catalog is not available.")
        conn.execute("BEGIN")  # uma só visão do banco por operação (ex.: GetTable + partições)
        try:
            return glue_ops.READ_OPERATIONS[name](conn, params)
        finally:
            conn.execute("ROLLBACK")


@router.post("/glue")
@router.post("/glue/")
async def glue(request: Request) -> Response:
    """Uma operação AWS Glue; o caminho com e sem `/` final é aceito (o SDK Java usa a barra)."""
    request_id = str(uuid.uuid4())
    operation = "-"
    try:
        auth = await _check_headers(request)
        body = await _read_body(request)
        _verify_signature(request, body, auth)
        operation = _operation(request)
        params = _params(request, body)
        result = await asyncio.to_thread(_execute, _home(request), operation, params)
        return JSONResponse(result, media_type=MEDIA_TYPE, headers={"x-amzn-RequestId": request_id})
    except AwsError as exc:
        return _error_response(exc, request_id)
    except glue_repo.GlueError as exc:
        return _error_response(_domain_error(exc), request_id)
    except Exception:
        log.exception("falha interna no endpoint glue (operação %s)", operation)
        return _error_response(AwsError(500, "InternalServiceException", "Internal failure."), request_id)
