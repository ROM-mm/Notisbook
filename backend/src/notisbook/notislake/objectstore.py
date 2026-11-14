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

_MESSAGES = {
    AUTH_FAILED: "o destino S3 recusou as credenciais",
    UNREACHABLE: "não foi possível conectar ao destino S3",
    TIMEOUT: "o destino S3 não respondeu no prazo",
    REDIRECT_REFUSED: "o destino S3 respondeu com redirecionamento, que não é seguido",
    BUCKET_MISSING: f"o bucket '{BUCKET}' não existe no destino S3",
    INVALID_TOKEN: "token de continuação inválido",
    UPSTREAM_ERROR: "o destino S3 respondeu com erro",
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


_cache_lock = threading.Lock()
_cache: tuple[tuple[Connection, int], Any] | None = None


def make_client(connection: Connection, *, retries: int = _LIST_RETRIES) -> Any:
    """Cliente S3 path-style para `connection`, com cache de uma posição (a chave inclui os retries)."""
    global _cache
    key = (connection, retries)
    with _cache_lock:
        if _cache is not None and _cache[0] == key:
            return _cache[1]
        client = _build_client(connection, retries)
        _cache = (key, client)
        return client


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
    client = boto3.client(
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
