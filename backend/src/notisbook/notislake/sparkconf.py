"""Opções S3A do bucket do notislake a partir da conexão resolvida (módulo puro, sem I/O).

Só gera chaves `fs.s3a.bucket.notislake.*`: a configuração por bucket não afeta outros destinos S3.
O resultado carrega o segredo, então `repr`/`str` o mascaram; quem grava na sessão Spark usa `items()`.
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


class S3AOptions(dict[str, str]):
    """Mapa de opções S3A; `repr`/`str` nunca exibem o valor do segredo."""

    def __repr__(self) -> str:
        shown = {key: ("***" if key == _SECRET_KEY else value) for key, value in self.items()}
        return f"S3AOptions({shown!r})"

    __str__ = __repr__


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
