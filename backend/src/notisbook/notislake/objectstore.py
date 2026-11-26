"""Acesso ao object store: resolução automático × manual, cliente S3, listagem, sonda e gestão de buckets.

O boto3 só é importado dentro das funções que o usam. Falhas do upstream viram
`ObjectStoreError` com código categórico e mensagem fixa: nada do que o servidor remoto
devolve (corpo, cabeçalhos, texto de exceção) chega ao chamador, e o segredo nunca aparece em
`repr` nem em mensagem. Quem expõe isso por HTTP mapeia os códigos para 502/504, nunca 401/403.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from . import settings_store
from .bootstrap import BUCKET, PREFIXES
from .locations import valid_bucket_name

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .supervisor import LocalConnection

logger = logging.getLogger(__name__)

_AUTOMATIC_REGION = "us-east-1"
_AUTOMATIC_CONNECT_TIMEOUT_S = 5.0
_AUTOMATIC_READ_TIMEOUT_S = 10.0
# `max_attempts` do botocore conta retries além da 1ª tentativa.
_LIST_RETRIES = 1
_PROBE_RETRIES = 0  # o prazo do teste é o timeout configurado, sem multiplicar por tentativas
_BUCKET_RETRIES = 0  # um retry após timeout com sucesso no servidor viraria um falso "já existe"/"não existe"
_PREFIX_FORBIDDEN_RE = re.compile(r"[\x00-\x1f\x7f\\]")  # controle e barra invertida
DELETE_BATCH_SIZE = 1000  # máximo de chaves por `DeleteObjects`

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
BUCKET_EXISTS = "bucket_exists"
BUCKET_NOT_EMPTY = "bucket_not_empty"

_MESSAGES = {
    AUTH_FAILED: "o destino S3 recusou as credenciais",
    UNREACHABLE: "não foi possível conectar ao destino S3",
    TIMEOUT: "o destino S3 não respondeu no prazo",
    REDIRECT_REFUSED: "o destino S3 respondeu com redirecionamento, que não é seguido",
    BUCKET_MISSING: "o bucket não existe no destino S3",
    INVALID_TOKEN: "token de continuação inválido",
    UPSTREAM_ERROR: "o destino S3 respondeu com erro",
    OBJECT_MISSING: "o objeto não existe no destino S3",
    ALREADY_EXISTS: "o objeto já existe no destino S3",
    TOO_LARGE: "o objeto excede o limite de leitura",
    BUCKET_EXISTS: "o bucket já existe no destino S3",
    BUCKET_NOT_EMPTY: "o bucket não está vazio",
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
_BUCKET_EXISTS_CODES = frozenset({"BucketAlreadyOwnedByYou", "BucketAlreadyExists"})
_BUCKET_NOT_EMPTY_CODES = frozenset({"BucketNotEmpty"})
# Falhas que repetir chave a chave não resolve: o recuo do `DeleteObjects` só vale para recusa do próprio lote.
_NO_FALLBACK = frozenset({AUTH_FAILED, UNREACHABLE, TIMEOUT, REDIRECT_REFUSED, BUCKET_MISSING})


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
    *,
    bucket: str = BUCKET,
) -> Page:
    """Uma página de `list_objects_v2` em `bucket` (padrão `notislake`), com delimitador `/`.

    O marcador de 0 byte do próprio `prefix` (ex.: `bronze/`) não entra em `objects`; por isso uma
    página pode vir com um item a menos que `max_keys`.
    """
    params: dict[str, Any] = {"Bucket": bucket, "Delimiter": "/", "MaxKeys": max_keys}
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


def probe(connection: Connection, *, bucket: str = BUCKET) -> None:
    """`head_bucket` em `bucket` (padrão `notislake`), sem seguir redirect; levanta `ObjectStoreError` se falhar."""
    try:
        make_client(connection, retries=_PROBE_RETRIES).head_bucket(Bucket=bucket)
    except _upstream_errors() as exc:
        raise _classify(exc) from None


def get_bounded(connection: Connection, key: str, *, max_bytes: int, bucket: str = BUCKET) -> bytes:
    """Conteúdo de `key` com no máximo `max_bytes`; `OBJECT_MISSING` se não existe, `TOO_LARGE` se excede."""
    _check_key(key)
    if max_bytes < 0:
        raise ValueError("max_bytes deve ser >= 0")
    try:
        response = make_client(connection).get_object(Bucket=bucket, Key=key)
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


def put_exclusive(connection: Connection, key: str, body: bytes, *, bucket: str = BUCKET) -> None:
    """Grava `key` só se ela não existir (`IfNoneMatch="*"`); se existir levanta `ObjectStoreError(ALREADY_EXISTS)`."""
    _check_key(key)
    try:
        make_client(connection, retries=_PUT_RETRIES).put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
    except _upstream_errors() as exc:
        raise _classify_object(exc, exclusive=True) from None


def delete_key(connection: Connection, key: str, *, bucket: str = BUCKET) -> None:
    """Remove um único objeto; é idempotente (chave ausente não é erro). Não há exclusão por prefixo."""
    _check_key(key)
    _delete_one(connection, bucket, key)


def _delete_one(connection: Connection, bucket: str, key: str) -> None:
    """`delete_object` sem `_check_key`: as chaves vindas da listagem incluem marcadores de pasta (`bronze/`)."""
    try:
        make_client(connection).delete_object(Bucket=bucket, Key=key)
    except _upstream_errors() as exc:
        raise _classify_object(exc) from None


def list_buckets(connection: Connection) -> list[str]:
    """Nomes de todos os buckets do destino, em ordem alfabética."""
    try:
        response = make_client(connection).list_buckets()
    except _upstream_errors() as exc:
        raise _classify(exc) from None
    return sorted(item["Name"] for item in response.get("Buckets", []))


def create_bucket_with_folders(connection: Connection, bucket: str) -> None:
    """Cria `bucket` e os marcadores de 0 byte de `bootstrap.PREFIXES`.

    `ValueError` se o nome violar `locations.valid_bucket_name`; `ObjectStoreError(BUCKET_EXISTS)`
    se o bucket já existir (nenhum marcador é gravado nesse caso).
    """
    if not valid_bucket_name(bucket):
        raise ValueError("nome de bucket inválido")
    client = make_client(connection, retries=_BUCKET_RETRIES)
    try:
        client.create_bucket(Bucket=bucket)
    except _upstream_errors() as exc:
        raise _classify_bucket(exc) from None
    try:
        for prefix in PREFIXES:
            client.put_object(Bucket=bucket, Key=prefix, Body=b"")
    except _upstream_errors() as exc:
        error = _classify_bucket(exc)
        _undo_create(client, bucket)
        raise error from None


def _undo_create(client: Any, bucket: str) -> None:
    """Desfaz, em melhor esforço, um `create_bucket` cujos marcadores falharam, para o retry não dar 409.

    Apaga todos os `PREFIXES` (delete de chave ausente é no-op no S3), pois a falha pode ter
    deixado o PUT incerto. Falhas aqui são só registradas (sem nome de bucket) e nunca substituem o erro original.
    """
    try:
        for key in PREFIXES:
            client.delete_object(Bucket=bucket, Key=key)
        client.delete_bucket(Bucket=bucket)
    except _upstream_errors():
        logger.warning("notislake: falha ao desfazer a criação do bucket após erro nos marcadores")


def iter_key_pages(connection: Connection, bucket: str, prefix: str = "") -> Iterator[list[str]]:
    """Gera as chaves sob `prefix` (vazio = bucket inteiro) uma página por vez, sem delimitador.

    Inclui os marcadores de pasta. `prefix` não vazio precisa terminar em `/`, para que `bronze/`
    nunca alcance `bronze2/`. Só uma página fica em memória; o consumidor pode apagar as chaves
    recebidas antes de pedir a próxima. Páginas vazias não são geradas.
    """
    _check_prefix(prefix)
    params: dict[str, Any] = {"Bucket": bucket}
    if prefix:
        params["Prefix"] = prefix
    client = make_client(connection)
    try:
        while True:
            response = client.list_objects_v2(**params)
            keys = [item["Key"] for item in response.get("Contents", [])]
            if keys:
                yield keys
            token = response.get("NextContinuationToken")
            if not response.get("IsTruncated") or not token:
                return
            params["ContinuationToken"] = token
    except _upstream_errors() as exc:
        raise _classify(exc) from None


def count_keys_under(connection: Connection, bucket: str, prefix: str = "") -> int:
    """Quantidade de chaves sob `prefix` (inclui marcadores de pasta), contada página a página sem acumulá-las."""
    return sum(len(page) for page in iter_key_pages(connection, bucket, prefix))


def delete_keys(connection: Connection, bucket: str, keys: list[str]) -> int:
    """Remove `keys` em lotes de até `DELETE_BATCH_SIZE` via `DeleteObjects` e devolve quantas processou.

    Chave ausente não é erro. Se o servidor recusar o lote (ou apontar falha por chave), recua para
    `delete_object` chave a chave nesse lote; falhas de conexão, credencial ou bucket inexistente
    sobem direto, pois repetir por chave não as resolveria.
    """
    if any(not key for key in keys):
        raise ValueError("chave de objeto inválida")
    client = make_client(connection)
    for start in range(0, len(keys), DELETE_BATCH_SIZE):
        batch = keys[start : start + DELETE_BATCH_SIZE]
        try:
            response = client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )
        except _upstream_errors() as exc:
            error = _classify_object(exc)
            if error.code in _NO_FALLBACK:
                raise error from None
            failed = batch
        else:
            failed = [item["Key"] for item in response.get("Errors", []) if "Key" in item]
        for key in failed:
            _delete_one(connection, bucket, key)
    return len(keys)


def delete_bucket(connection: Connection, bucket: str) -> None:
    """Remove `bucket` vazio, sem `x-minio-force-delete`.

    Bucket com objetos levanta `ObjectStoreError(BUCKET_NOT_EMPTY)`; inexistente, `BUCKET_MISSING`.
    """
    try:
        make_client(connection, retries=_BUCKET_RETRIES).delete_bucket(Bucket=bucket)
    except _upstream_errors() as exc:
        raise _classify_bucket(exc) from None


def _check_key(key: str) -> None:
    """Recusa chave vazia, com `/` inicial ou final, `.` ou `..`; segmento vazio (`a//b.csv`) é válido."""
    if not key or key.startswith("/") or key.endswith("/") or any(part in (".", "..") for part in key.split("/")):
        raise ValueError("chave de objeto inválida")


def _check_prefix(prefix: str) -> None:
    """Aceita prefixo vazio ou terminado em `/`, sem `/` inicial, controle, `\\`, `.` ou `..`.

    Segmentos vazios (`a//`) são válidos: o S3 aceita chaves como `a//b.csv` e a pasta precisa
    poder ser contada e excluída. Mantém a mesma regra de segurança de `api.notislake._check_prefix`.
    """
    if not prefix:
        return
    if (
        not prefix.endswith("/")
        or prefix.startswith("/")
        or _PREFIX_FORBIDDEN_RE.search(prefix)
        or any(part in (".", "..") for part in prefix[:-1].split("/"))
    ):
        raise ValueError("prefixo inválido")


def _classify_bucket(exc: Exception) -> ObjectStoreError:
    """Como `_classify`, mas distingue bucket já existente e bucket não vazio."""
    from botocore.exceptions import ClientError

    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in _BUCKET_EXISTS_CODES:
            return ObjectStoreError(BUCKET_EXISTS)
        if code in _BUCKET_NOT_EMPTY_CODES:
            return ObjectStoreError(BUCKET_NOT_EMPTY)
    return _classify(exc)


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
