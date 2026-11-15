"""Acesso ao bucket `notislake`: resolução automático × manual, cliente S3, listagem e sonda.

O boto3 só é importado dentro das funções que o usam. Falhas do upstream viram
`ObjectStoreError` com código categórico e mensagem fixa: nada do que o servidor remoto
devolve (corpo, cabeçalhos, texto de exceção) chega ao chamador, e o segredo nunca aparece em
`repr` nem em mensagem. Quem expõe isso por HTTP mapeia os códigos para 502/504, nunca 401/403.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from . import settings_store
from .bootstrap import BUCKET

if TYPE_CHECKING:
    from .supervisor import LocalConnection

_AUTOMATIC_REGION = "us-east-1"
_AUTOMATIC_CONNECT_TIMEOUT_S = 5.0
_AUTOMATIC_READ_TIMEOUT_S = 10.0
# `max_attempts` do botocore conta retries além da 1ª tentativa.
_LIST_RETRIES = 1
_PROBE_RETRIES = 0  # o prazo do teste é o timeout configurado, sem multiplicar por tentativas

AUTH_FAILED = "auth_failed"
UNREACHABLE = "unreachable"
TIMEOUT = "timeout"
REDIRECT_REFUSED = "redirect_refused"
BUCKET_MISSING = "bucket_missing"
INVALID_TOKEN = "invalid_continuation_token"
UPSTREAM_ERROR = "upstream_error"
OBJECT_MISSING = "object_missing"
ALREADY_EXISTS = "already_exists"
TOO_LARGE = "too_large"

_MESSAGES = {
    AUTH_FAILED: "o destino S3 recusou as credenciais",
    UNREACHABLE: "não foi possível conectar ao destino S3",
    TIMEOUT: "o destino S3 não respondeu no prazo",
    REDIRECT_REFUSED: "o destino S3 respondeu com redirecionamento, que não é seguido",
    BUCKET_MISSING: f"o bucket '{BUCKET}' não existe no destino S3",
    INVALID_TOKEN: "token de continuação inválido",
    UPSTREAM_ERROR: "o destino S3 respondeu com erro",
    OBJECT_MISSING: "o objeto não existe no destino S3",
    ALREADY_EXISTS: "o objeto já existe no destino S3",
    TOO_LARGE: "o objeto excede o limite de leitura",
}
_AUTH_CODES = frozenset(
    {
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "AccessDenied",
        "AllAccessDisabled",
        "InvalidToken",
        "ExpiredToken",
        "AuthorizationHeaderMalformed",
        "AccountProblem",
        "403",
        "401",
    }
)
_REDIRECT_CODES = frozenset({"PermanentRedirect", "TemporaryRedirect", "Redirect"})
_BUCKET_MISSING_CODES = frozenset({"NoSuchBucket", "404"})
# O MinIO responde 501 NotImplemented a um ContinuationToken que ele não reconhece.
_TOKEN_CODES = frozenset({"InvalidArgument", "InvalidContinuationToken", "NotImplemented"})
_TOKEN_STATUSES = frozenset({400, 501})
_OBJECT_MISSING_CODES = frozenset({"NoSuchKey"})
# 412 quando a chave existe; 409 quando outra gravação condicional concorre pela mesma chave.
_EXISTS_CODES = frozenset({"PreconditionFailed", "ConditionalRequestConflict"})
_EXISTS_STATUSES = frozenset({409, 412})
_PUT_RETRIES = 0  # um retry após timeout com sucesso no servidor viraria um falso "já existe"


class Unavailable(Exception):
    """Sem conexão utilizável: sem configuração manual e o MinIO local não está em `running`."""


class ObjectStoreError(Exception):
    """Falha do destino S3; `code` é categórico e `str(exc)` é uma mensagem fixa."""

    def __init__(self, code: str) -> None:
        super().__init__(_MESSAGES.get(code, _MESSAGES[UPSTREAM_ERROR]))
        self.code = code


@dataclass(frozen=True)
class Connection:
    source: Literal["automatic", "manual"]
    endpoint: str
    access_key: str
    secret_key: str = field(repr=False)
    region: str
    connect_timeout_s: float
    read_timeout_s: float

    def __repr__(self) -> str:
        return (
            f"Connection(source={self.source!r}, endpoint={self.endpoint!r}, access_key={self.access_key!r}, "
            f"secret_key='***', region={self.region!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    last_modified: datetime | None


@dataclass(frozen=True)
class Page:
    prefixes: list[str]
    objects: list[ObjectInfo]
    is_truncated: bool
    next_continuation_token: str | None


class _Supervisor(Protocol):
    def connection(self) -> LocalConnection | None: ...


def resolve(home: Path, supervisor: _Supervisor) -> Connection:
    """Manual válido → manual; manual inválido → `ConfigInvalid`; sem arquivo → MinIO local ou `Unavailable`."""
    manual = settings_store.load(home)
    if manual is not None:
        return Connection(
            source="manual",
            endpoint=manual.endpoint,
            access_key=manual.access_key,
            secret_key=manual.secret_key,
            region=manual.region,
            connect_timeout_s=float(manual.timeout_s),
            read_timeout_s=float(manual.timeout_s),
        )
    local = supervisor.connection()
    if local is None:
        raise Unavailable("MinIO local indisponível")
    return Connection(
        source="automatic",
        endpoint=local.endpoint,
        access_key=local.access_key,
        secret_key=local.secret_key,
        region=_AUTOMATIC_REGION,
        connect_timeout_s=_AUTOMATIC_CONNECT_TIMEOUT_S,
        read_timeout_s=_AUTOMATIC_READ_TIMEOUT_S,
    )


class _NoSupervisor:
    def connection(self) -> None:
        return None


def resolve_from_app(home: Path, supervisor: _Supervisor | None) -> Connection:
    """`resolve` para quem pode estar sem supervisor (app embutido, testes): só a conexão manual vale."""
    return resolve(home, supervisor if supervisor is not None else _NoSupervisor())


_cache_lock = threading.Lock()
_cache: tuple[Connection, dict[int, Any]] | None = None


def make_client(connection: Connection, *, retries: int = _LIST_RETRIES) -> Any:
    """Cliente S3 path-style para `connection`, reaproveitado por perfil de retries; só a conexão mais recente fica em cache."""
    global _cache
    with _cache_lock:
        if _cache is None or _cache[0] != connection:
            _cache = (connection, {})
        clients = _cache[1]
        if retries not in clients:
            clients[retries] = _build_client(connection, retries)
        return clients[retries]


def _build_client(connection: Connection, retries: int) -> Any:
    import boto3
    from botocore.config import Config

    options: dict[str, Any] = {}
    if connection.source == "automatic":
        options["proxies"] = {}  # {} (e não None) desliga o proxy do ambiente na sonda de loopback
    config = Config(
        s3={"addressing_style": "path"},
        # Destinos S3 compatíveis nem sempre aceitam os checksums que o boto3 >= 1.36 envia por padrão.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        connect_timeout=connection.connect_timeout_s,
        read_timeout=connection.read_timeout_s,
        retries={"max_attempts": retries, "mode": "standard"},
        **options,
    )
    client = boto3.session.Session().client(
        "s3",
        endpoint_url=connection.endpoint,
        aws_access_key_id=connection.access_key,
        aws_secret_access_key=connection.secret_key,
        region_name=connection.region,
        config=config,
    )
    _refuse_redirects(client)
    return client


def _refuse_redirects(client: Any) -> None:
    """Impede o botocore de reenviar a requisição assinada após um redirect (301/307/PermanentRedirect).

    O redirector interno do botocore ignora requisições cujo contexto já consta como redirecionado;
    marcá-lo antes da chamada o desliga sem depender de atributo privado do cliente.
    """

    def mark_redirected(params: dict[str, Any], **_: Any) -> None:
        params.setdefault("context", {}).setdefault("s3_redirect", {})["redirected"] = True

    client.meta.events.register("before-call.s3", mark_redirected)


def list_page(
    connection: Connection,
    prefix: str = "",
    max_keys: int = 100,
    continuation_token: str | None = None,
) -> Page:
    """Uma página de `list_objects_v2` no bucket `notislake`, com delimitador `/`.

    O marcador de 0 byte do próprio `prefix` (ex.: `bronze/`) não entra em `objects`; por isso uma
    página pode vir com um item a menos que `max_keys`.
    """
    params: dict[str, Any] = {"Bucket": BUCKET, "Delimiter": "/", "MaxKeys": max_keys}
    if prefix:
        params["Prefix"] = prefix
    if continuation_token:
        params["ContinuationToken"] = continuation_token
    try:
        response = make_client(connection).list_objects_v2(**params)
    except _upstream_errors() as exc:
        raise _classify(exc, token_given=bool(continuation_token)) from None
    objects = [
        ObjectInfo(key=item["Key"], size=int(item.get("Size", 0)), last_modified=item.get("LastModified"))
        for item in response.get("Contents", [])
        if item["Key"] != prefix
    ]
    return Page(
        prefixes=[item["Prefix"] for item in response.get("CommonPrefixes", [])],
        objects=objects,
        is_truncated=bool(response.get("IsTruncated", False)),
        next_continuation_token=response.get("NextContinuationToken") if response.get("IsTruncated") else None,
    )


def probe(connection: Connection) -> None:
    """`head_bucket` no bucket `notislake`, sem seguir redirect; levanta `ObjectStoreError` se falhar."""
    try:
        make_client(connection, retries=_PROBE_RETRIES).head_bucket(Bucket=BUCKET)
    except _upstream_errors() as exc:
        raise _classify(exc) from None


def get_bounded(connection: Connection, key: str, *, max_bytes: int) -> bytes:
    """Conteúdo de `key` com no máximo `max_bytes`; `OBJECT_MISSING` se não existe, `TOO_LARGE` se excede."""
    _check_key(key)
    if max_bytes < 0:
        raise ValueError("max_bytes deve ser >= 0")
    try:
        response = make_client(connection).get_object(Bucket=BUCKET, Key=key)
        body = response["Body"]
        try:
            declared = response.get("ContentLength")
            if declared is not None and int(declared) > max_bytes:
                raise ObjectStoreError(TOO_LARGE)
            data = body.read(max_bytes + 1)
        finally:
            body.close()
    except _upstream_errors() as exc:
        raise _classify_object(exc) from None
    if len(data) > max_bytes:
        raise ObjectStoreError(TOO_LARGE)
    return data


def put_exclusive(connection: Connection, key: str, body: bytes) -> None:
    """Grava `key` só se ela não existir (`IfNoneMatch="*"`); se existir levanta `ObjectStoreError(ALREADY_EXISTS)`."""
    _check_key(key)
    try:
        make_client(connection, retries=_PUT_RETRIES).put_object(Bucket=BUCKET, Key=key, Body=body, IfNoneMatch="*")
    except _upstream_errors() as exc:
        raise _classify_object(exc, exclusive=True) from None


def delete_key(connection: Connection, key: str) -> None:
    """Remove um único objeto; é idempotente (chave ausente não é erro). Não há exclusão por prefixo."""
    _check_key(key)
    try:
        make_client(connection).delete_object(Bucket=BUCKET, Key=key)
    except _upstream_errors() as exc:
        raise _classify_object(exc) from None


def _check_key(key: str) -> None:
    """Recusa chave vazia, com `/` inicial ou final e segmentos vazios, `.` ou `..` (nunca um prefixo)."""
    if not key or any(part in ("", ".", "..") for part in key.split("/")):
        raise ValueError("chave de objeto inválida")


def _classify_object(exc: Exception, *, exclusive: bool = False) -> ObjectStoreError:
    """Como `_classify`, mas distingue chave ausente e, com `exclusive`, gravação recusada por 409/412."""
    from botocore.exceptions import ClientError

    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
        if code in _OBJECT_MISSING_CODES:
            return ObjectStoreError(OBJECT_MISSING)
        if exclusive and (code in _EXISTS_CODES or status in _EXISTS_STATUSES):
            return ObjectStoreError(ALREADY_EXISTS)
    return _classify(exc)


def _upstream_errors() -> tuple[type[Exception], ...]:
    from botocore.exceptions import BotoCoreError, ClientError

    return (BotoCoreError, ClientError)


def _classify(exc: Exception, *, token_given: bool = False) -> ObjectStoreError:
    """Traduz a exceção do botocore para um código categórico, sem reaproveitar o texto dela."""
    from botocore.exceptions import (
        ClientError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )
    from botocore.exceptions import ConnectionError as BotoConnectionError

    if isinstance(exc, ConnectTimeoutError | ReadTimeoutError):
        return ObjectStoreError(TIMEOUT)
    if isinstance(exc, EndpointConnectionError | BotoConnectionError):
        return ObjectStoreError(UNREACHABLE)
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
        if code in _REDIRECT_CODES or 300 <= status < 400:
            return ObjectStoreError(REDIRECT_REFUSED)
        if code in _AUTH_CODES or status in (401, 403):
            return ObjectStoreError(AUTH_FAILED)
        if code in _BUCKET_MISSING_CODES or status == 404:
            return ObjectStoreError(BUCKET_MISSING)
        if token_given and (code in _TOKEN_CODES or status in _TOKEN_STATUSES):
            return ObjectStoreError(INVALID_TOKEN)
    return ObjectStoreError(UPSTREAM_ERROR)
