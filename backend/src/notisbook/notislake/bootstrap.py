"""Preparação do MinIO local: espera da prontidão e criação do layout do lake.

O boto3 é importado só dentro de `ensure_layout` para não pesar no import do backend.
Nenhuma mensagem de erro contém credencial.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable

from .credentials import Credentials
from .locations import BUCKET, MANAGED_BUCKET
from .ports import LOOPBACK

# Pastas iniciais do `notislake`: só organização para o dev, sem significado para o catálogo.
PREFIXES = tuple(f"{zone}/" for zone in ("landing", "bronze", "silver", "gold"))
READY_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 0.25
_PROBE_TIMEOUT_S = 2.0
# Opener sem ProxyHandler: HTTP(S)_PROXY do ambiente não pode desviar a sonda de loopback.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BootstrapError(Exception):
    """Falha ao preparar o layout do lake; a mensagem nunca contém credencial."""


def wait_ready(
    port: int,
    timeout: float = READY_TIMEOUT_S,
    *,
    is_alive: Callable[[], bool] | None = None,
) -> bool:
    """Sonda `/minio/health/ready` em 127.0.0.1:`port` até responder 200 ou vencer `timeout`.

    Devolve False no prazo esgotado ou quando `is_alive` (se dado) indica que o processo morreu.
    """
    url = f"http://{LOOPBACK}:{port}/minio/health/ready"
    deadline = time.monotonic() + timeout
    while True:
        if is_alive is not None and not is_alive():
            return False
        try:
            with _NO_PROXY_OPENER.open(url, timeout=_PROBE_TIMEOUT_S) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass  # ainda subindo (conexão recusada, reset ou 503)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(_POLL_INTERVAL_S, remaining))


def _client(port: int, credentials: Credentials):  # noqa: ANN202 - cliente boto3, importado sob demanda
    import boto3
    from botocore.config import Config

    config = Config(
        s3={"addressing_style": "path"},
        # O MinIO não exige os checksums adicionais que o boto3 >= 1.36 envia por padrão.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        proxies={},  # {} (e não None) desliga o proxy do ambiente
        connect_timeout=5,
        read_timeout=10,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return boto3.session.Session().client(
        "s3",
        endpoint_url=f"http://{LOOPBACK}:{port}",
        aws_access_key_id=credentials.user,
        aws_secret_access_key=credentials.password,
        region_name="us-east-1",
        config=config,
    )


def ensure_layout(port: int, credentials: Credentials) -> None:
    """Cria o bucket `notislake` e os prefixos `landing/ bronze/ silver/ gold/`, de forma idempotente.

    Os prefixos são marcadores de 0 byte; repetir a chamada não altera objetos existentes além deles.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client(port, credentials)
    try:
        try:
            client.create_bucket(Bucket=BUCKET)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
        for prefix in PREFIXES:
            client.put_object(Bucket=BUCKET, Key=prefix, Body=b"")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "unknown")
        raise BootstrapError(f"falha ao preparar o bucket '{BUCKET}' no MinIO local ({code})") from None
    except BotoCoreError as exc:
        raise BootstrapError(
            f"falha ao preparar o bucket '{BUCKET}' no MinIO local ({type(exc).__name__})"
        ) from None


def ensure_managed_bucket(port: int, credentials: Credentials) -> None:
    """Cria o bucket reservado `notisbook-managed` se faltar, sem prefixos; idempotente e seguro a cada subida.

    Só o `notislake` tem marcador de primeira inicialização: o reservado é do app e precisa existir sempre.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client(port, credentials)
    try:
        client.create_bucket(Bucket=MANAGED_BUCKET)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "unknown")
        if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise BootstrapError(f"falha ao preparar o bucket reservado do app no MinIO local ({code})") from None
    except BotoCoreError as exc:
        raise BootstrapError(
            f"falha ao preparar o bucket reservado do app no MinIO local ({type(exc).__name__})"
        ) from None
