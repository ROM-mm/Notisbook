"""Opções S3A do bucket do notislake a partir da conexão resolvida (módulo puro, sem I/O).

Só gera chaves `fs.s3a.bucket.notislake.*`: a configuração por bucket não afeta outros destinos S3.
O resultado de `s3a_options` carrega o segredo, então `repr`/`str` o mascaram; quem grava na sessão
Spark usa `items()`. `closed_options` é a config fechada (sem segredo) para processos sem o hook.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..config import RUNTIME_HOST
from .bootstrap import BUCKET
from .settings_store import is_loopback_host

if TYPE_CHECKING:
    from .objectstore import Connection

_PREFIX = f"fs.s3a.bucket.{BUCKET}."
_SECRET_KEY = f"{_PREFIX}secret.key"
_CREDENTIALS_PROVIDER = "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
_ANONYMOUS_PROVIDER = "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider"
_DEAD_ENDPOINT = "http://127.0.0.1:1"
# Sem retry/timeout curtos, uma queda do MinIO prende a célula por minutos (padrões do Hadoop).
_RETRIES = "2"
_CONNECT_TIMEOUT_MS = "5000"
_SOCKET_TIMEOUT_MS = "60000"


class S3AOptions(dict[str, str]):
    """Mapa de opções S3A; `repr`/`str` nunca exibem o valor do segredo."""

    def __repr__(self) -> str:
        shown = {key: ("***" if key == _SECRET_KEY else value) for key, value in self.items()}
        return f"S3AOptions({shown!r})"

    __str__ = __repr__


def closed_options() -> dict[str, str]:
    """Config fechada do bucket: endpoint morto, credencial anônima, sem segredo e sem retry.

    Fonte única para spark-defaults, hook e Docker; a conexão real a sobrescreve via `s3a_options`.
    """
    return {
        f"{_PREFIX}endpoint": _DEAD_ENDPOINT,
        f"{_PREFIX}path.style.access": "true",
        f"{_PREFIX}connection.ssl.enabled": "false",
        f"{_PREFIX}aws.credentials.provider": _ANONYMOUS_PROVIDER,
        f"{_PREFIX}attempts.maximum": "1",
        f"{_PREFIX}retry.limit": "0",
    }


def _container_endpoint(endpoint: str) -> str:
    """Troca host loopback por `host.lima.internal`, preservando esquema, porta e caminho."""
    parts = urlsplit(endpoint)
    host = parts.hostname
    if host is None or not is_loopback_host(host):
        return endpoint
    port = f":{parts.port}" if parts.port is not None else ""
    return parts._replace(netloc=f"{RUNTIME_HOST}{port}").geturl()


def s3a_options(conn: Connection, *, docker: bool) -> S3AOptions:
    """Opções `fs.s3a.bucket.notislake.*` da conexão; com `docker=True` o endpoint loopback vira `host.lima.internal`."""
    endpoint = _container_endpoint(conn.endpoint) if docker else conn.endpoint
    return S3AOptions(
        {
            f"{_PREFIX}endpoint": endpoint,
            f"{_PREFIX}endpoint.region": conn.region,
            f"{_PREFIX}access.key": conn.access_key,
            _SECRET_KEY: conn.secret_key,
            f"{_PREFIX}path.style.access": "true",
            f"{_PREFIX}connection.ssl.enabled": str(urlsplit(endpoint).scheme == "https").lower(),
            f"{_PREFIX}aws.credentials.provider": _CREDENTIALS_PROVIDER,
            f"{_PREFIX}attempts.maximum": _RETRIES,
            f"{_PREFIX}retry.limit": _RETRIES,
            f"{_PREFIX}connection.establish.timeout": _CONNECT_TIMEOUT_MS,
            f"{_PREFIX}connection.timeout": _SOCKET_TIMEOUT_MS,
        }
    )


def fingerprint(conn: Connection) -> str:
    """Identidade estável da conexão (origem, endpoint, região, chaves) para comparação; só o digest sai daqui."""
    digest = hashlib.sha256()
    for part in (conn.source, conn.endpoint, conn.region, conn.access_key, conn.secret_key):
        encoded = part.encode()
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()
