"""Opções S3A a partir da conexão resolvida (módulo puro, sem I/O).

Automático (MinIO local): chaves globais `fs.s3a.*` reais, de modo que qualquer bucket só alcance o MinIO local.
Manual (S3 externo): só `fs.s3a.bucket.<bucket>.*` dos buckets conhecidos (`notislake` e o reservado
`notisbook-managed`), sem afetar outros destinos S3. `scheme_options` mapeia `s3://`.
O resultado de `s3a_options` carrega o segredo, então `repr`/`str` o mascaram; quem grava na sessão
Spark usa `items()`. `closed_options` é a config fechada global (sem segredo) para processos sem o hook.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

from ..config import RUNTIME_HOST
from .locations import KNOWN_BUCKETS
from .settings_store import is_loopback_host

if TYPE_CHECKING:
    from .objectstore import Connection

_GLOBAL_PREFIX = "fs.s3a."
_BUCKET_PREFIXES = tuple(f"fs.s3a.bucket.{bucket}." for bucket in KNOWN_BUCKETS)
_SECRET_KEYS = frozenset({f"{_GLOBAL_PREFIX}secret.key", *(f"{prefix}secret.key" for prefix in _BUCKET_PREFIXES)})
# Hadoop: a chave por bucket vence a global; `bucket.probe=0` evita checar a existência do bucket ao criar o FileSystem.
_BUCKET_PROBE_KEY = "fs.s3a.bucket.probe"

S3AScope = Literal["any", "notislake"]
SCOPE_ANY: S3AScope = "any"
SCOPE_NOTISLAKE: S3AScope = "notislake"
_CREDENTIALS_PROVIDER = "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
_ANONYMOUS_PROVIDER = "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider"
_DEAD_ENDPOINT = "http://127.0.0.1:1"
_S3A_FS = "org.apache.hadoop.fs.s3a.S3AFileSystem"
_S3A_ABSTRACT_FS = "org.apache.hadoop.fs.s3a.S3A"
# Sem retry/timeout curtos, uma queda do MinIO prende a célula por minutos (padrões do Hadoop).
_RETRIES = "2"
_CONNECT_TIMEOUT_MS = "5000"
_SOCKET_TIMEOUT_MS = "60000"


class S3AOptions(dict[str, str]):
    """Mapa de opções S3A; `repr`/`str` nunca exibem o valor do segredo."""

    def __repr__(self) -> str:
        shown = {key: ("***" if key in _SECRET_KEYS else value) for key, value in self.items()}
        return f"S3AOptions({shown!r})"

    __str__ = __repr__


def s3a_scope(*, automatic: bool) -> S3AScope:
    """Escopo S3A do kernel: `any` no automático (config global, vale para todo bucket) e `notislake` no manual."""
    return SCOPE_ANY if automatic else SCOPE_NOTISLAKE


def closed_options() -> dict[str, str]:
    """Config fechada global: endpoint morto, credencial anônima, sem segredo e sem retry, para qualquer bucket.

    Fonte única para spark-defaults, hook e Docker; a conexão real a sobrescreve via `s3a_options`.
    """
    return {
        f"{_GLOBAL_PREFIX}endpoint": _DEAD_ENDPOINT,
        f"{_GLOBAL_PREFIX}path.style.access": "true",
        f"{_GLOBAL_PREFIX}connection.ssl.enabled": "false",
        f"{_GLOBAL_PREFIX}aws.credentials.provider": _ANONYMOUS_PROVIDER,
        f"{_GLOBAL_PREFIX}attempts.maximum": "1",
        f"{_GLOBAL_PREFIX}retry.limit": "0",
    }


def scheme_options() -> dict[str, str]:
    """Mapeia `s3://` para o S3A (sinônimo de `s3a://`); sem segredo. O PySpark local não traz esse mapeamento.

    As chaves `fs.s3a.*` de `closed_options`/`s3a_options` valem para os dois esquemas; o hook grava estas na sessão.
    """
    return {"fs.s3.impl": _S3A_FS, "fs.AbstractFileSystem.s3.impl": _S3A_ABSTRACT_FS}


def _container_endpoint(endpoint: str) -> str:
    """Troca host loopback por `host.lima.internal`, preservando esquema, porta e caminho."""
    parts = urlsplit(endpoint)
    host = parts.hostname
    if host is None or not is_loopback_host(host):
        return endpoint
    port = f":{parts.port}" if parts.port is not None else ""
    return parts._replace(netloc=f"{RUNTIME_HOST}{port}").geturl()


def s3a_options(conn: Connection, *, docker: bool, automatic: bool) -> S3AOptions:
    """Opções S3A da conexão; com `docker=True` o endpoint loopback vira `host.lima.internal`.

    `automatic=True` grava chaves globais `fs.s3a.*` (mais `fs.s3a.bucket.probe=0`, para bucket criado depois
    funcionar sem reiniciar); `False` grava só `fs.s3a.bucket.<bucket>.*` de cada bucket conhecido.
    """
    endpoint = _container_endpoint(conn.endpoint) if docker else conn.endpoint
    options = S3AOptions()
    for prefix in (_GLOBAL_PREFIX,) if automatic else _BUCKET_PREFIXES:
        options.update(
            {
                f"{prefix}endpoint": endpoint,
                f"{prefix}endpoint.region": conn.region,
                f"{prefix}access.key": conn.access_key,
                f"{prefix}secret.key": conn.secret_key,
                f"{prefix}path.style.access": "true",
                f"{prefix}connection.ssl.enabled": str(urlsplit(endpoint).scheme == "https").lower(),
                f"{prefix}aws.credentials.provider": _CREDENTIALS_PROVIDER,
                f"{prefix}attempts.maximum": _RETRIES,
                f"{prefix}retry.limit": _RETRIES,
                f"{prefix}connection.establish.timeout": _CONNECT_TIMEOUT_MS,
                f"{prefix}connection.timeout": _SOCKET_TIMEOUT_MS,
            }
        )
    if automatic:
        options[_BUCKET_PROBE_KEY] = "0"
    return options


def fingerprint(conn: Connection) -> str:
    """Identidade estável da conexão (origem, endpoint, região, chaves) para comparação; só o digest sai daqui."""
    digest = hashlib.sha256()
    for part in (conn.source, conn.endpoint, conn.region, conn.access_key, conn.secret_key):
        encoded = part.encode()
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()
