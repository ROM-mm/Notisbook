"""Conexão S3 manual do notislake, guardada em `<home>/notislake-connection.json` (0600).

O segredo fica em texto claro protegido pela permissão do arquivo e nunca aparece em `repr`,
em mensagens de erro nem em retorno de API (quem expõe a conexão usa `has_secret`). Nenhuma
mensagem de `ConfigInvalid` ecoa valor recebido. A leitura não usa cache: cada `load` relê o disco.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import stat
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

VERSION = 1
_FILE_NAME = "notislake-connection.json"
_FILE_MODE = 0o600
_MAX_FILE_BYTES = 64 * 1024
_NAME_MAX, _ACCESS_KEY_MAX, _SECRET_KEY_MAX, _REGION_MAX = 64, 128, 256, 64
_TIMEOUT_MIN, _TIMEOUT_MAX = 1, 120
_DEFAULT_PORTS = {"http": 80, "https": 443}
_REGION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]")
_lock = threading.Lock()


class ConfigInvalid(Exception):
    """Configuração manual inválida; a mensagem nunca contém valores recebidos nem o segredo."""

    def __init__(self, message: str, field_name: str | None = None) -> None:
        super().__init__(message)
        self.field = field_name


@dataclass(frozen=True)
class ManualConfig:
    name: str
    endpoint: str
    access_key: str
    secret_key: str = field(repr=False)
    region: str
    timeout_s: int | float

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_key)

    def __repr__(self) -> str:
        return (
            f"ManualConfig(name={self.name!r}, endpoint={self.endpoint!r}, access_key={self.access_key!r}, "
            f"secret_key='***', region={self.region!r}, timeout_s={self.timeout_s!r})"
        )

    __str__ = __repr__


def connection_path(home: Path) -> Path:
    return home / _FILE_NAME


def _text(value: object, name: str, max_len: int, *, allow_space: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigInvalid(f"{name} is required", name)
    if len(value) > max_len:
        raise ConfigInvalid(f"{name} is too long (max {max_len} characters)", name)
    pattern = re.compile(r"[\x00-\x1f\x7f]") if allow_space else _CONTROL_RE
    if pattern.search(value):
        raise ConfigInvalid(f"{name} has invalid characters", name)
    return value.strip() if allow_space else value


def _legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Interpreta formas abreviadas/decimais/hex de IPv4 (ex.: `127.1`, `2130706433`) como o resolvedor faria."""
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def _host_address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    bare = host.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(bare)
    except ValueError:
        return _legacy_ipv4(bare) if ":" not in bare else None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def is_loopback_host(host: str) -> bool:
    name = host.rstrip(".").lower()
    if name == "localhost" or name.endswith(".localhost"):
        return True
    address = _host_address(host)
    return address is not None and address.is_loopback


def normalize_endpoint(endpoint: object, *, backend_port: int | None = None) -> str:
    """Valida o endpoint e devolve a forma normalizada (`esquema://host[:porta][/caminho]`).

    Aceita só http/https, sem credencial, query ou fragmento. Recusa IP link-local literal e,
    quando `backend_port` é informado, loopback nessa porta (evita o painel apontar para o próprio backend).
    """
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ConfigInvalid("endpoint is required", "endpoint")
    raw = endpoint.strip()
    if len(raw) > 512 or _CONTROL_RE.search(raw):
        raise ConfigInvalid("endpoint is malformed", "endpoint")
    if "?" in raw or "#" in raw:
        raise ConfigInvalid("endpoint must not have query or fragment", "endpoint")
    try:
        parts = urlsplit(raw)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise ConfigInvalid("endpoint is malformed", "endpoint") from None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ConfigInvalid("endpoint must use http or https", "endpoint")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ConfigInvalid("endpoint must not embed credentials", "endpoint")
    if not host:
        raise ConfigInvalid("endpoint has no host", "endpoint")
    address = _host_address(host)
    if address is not None and address.is_link_local:
        raise ConfigInvalid("endpoint must not be a link-local address", "endpoint")
    effective = port if port is not None else _DEFAULT_PORTS[scheme]
    if backend_port is not None and effective == backend_port and is_loopback_host(host):
        raise ConfigInvalid("endpoint must not point to the Notisbook backend", "endpoint")
    shown = f"[{host.lower()}]" if ":" in host else host.lower()
    suffix = f":{port}" if port is not None and port != _DEFAULT_PORTS[scheme] else ""
    return f"{scheme}://{shown}{suffix}{parts.path.rstrip('/')}"


def _timeout(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigInvalid("timeout_s must be a number", "timeout_s")
    if not _TIMEOUT_MIN <= value <= _TIMEOUT_MAX:  # NaN também cai aqui (comparação falsa)
        raise ConfigInvalid(f"timeout_s must be between {_TIMEOUT_MIN} and {_TIMEOUT_MAX}", "timeout_s")
    return value


def _build(data: dict[str, object], *, backend_port: int | None) -> ManualConfig:
    region = _text(data.get("region"), "region", _REGION_MAX)
    if not _REGION_RE.match(region):
        raise ConfigInvalid("region has invalid characters", "region")
    return ManualConfig(
        name=_text(data.get("name"), "name", _NAME_MAX, allow_space=True),
        endpoint=normalize_endpoint(data.get("endpoint"), backend_port=backend_port),
        access_key=_text(data.get("access_key"), "access_key", _ACCESS_KEY_MAX),
        secret_key=_text(data.get("secret_key"), "secret_key", _SECRET_KEY_MAX),
        region=region,
        timeout_s=_timeout(data.get("timeout_s")),
    )


def validate(
    *,
    name: object,
    endpoint: object,
    access_key: object,
    secret_key: object,
    region: object,
    timeout_s: object,
    backend_port: int,
    current: ManualConfig | None = None,
) -> ManualConfig:
    """Valida um rascunho e devolve a `ManualConfig` normalizada; levanta `ConfigInvalid` sem ecoar valores.

    `secret_key` vazio ou ausente reaproveita o de `current`, e só quando o endpoint normalizado e
    a `access_key` são os mesmos; caso contrário o segredo é exigido de novo.
    """
    normalized = normalize_endpoint(endpoint, backend_port=backend_port)
    if secret_key is None or secret_key == "":
        reusable = (
            current is not None
            and current.endpoint == normalized
            and isinstance(access_key, str)
            and current.access_key == access_key
        )
        if not reusable or current is None:
            raise ConfigInvalid("secret_key is required when endpoint or access_key changes", "secret_key")
        secret_key = current.secret_key
    return _build(
        {
            "name": name,
            "endpoint": endpoint,
            "access_key": access_key,
            "secret_key": secret_key,
            "region": region,
            "timeout_s": timeout_s,
        },
        backend_port=backend_port,
    )


def _read(path: Path) -> ManualConfig:
    """Lê sem seguir symlink, corrige permissão aberta (com aviso em stderr) e valida o conteúdo."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ConfigInvalid(f"cannot read {path} ({exc.strerror})") from None
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ConfigInvalid(f"{path} is not a regular file")
        if stat.S_IMODE(info.st_mode) & 0o077:
            os.fchmod(handle.fileno(), _FILE_MODE)
            print(f"Notisbook: permissões de {path} estavam abertas; ajustadas para 0600.", file=sys.stderr)
        content = handle.read(_MAX_FILE_BYTES + 1)
    if len(content) > _MAX_FILE_BYTES:
        raise ConfigInvalid(f"{path} is too large")
    try:
        data = json.loads(content.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ConfigInvalid(f"{path} is not valid JSON") from None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ConfigInvalid(f"{path} has unexpected content")
    try:
        return _build(data, backend_port=None)
    except ConfigInvalid as exc:
        raise ConfigInvalid(f"{path} has an invalid {exc.field or 'content'}", exc.field) from None


def load(home: Path) -> ManualConfig | None:
    """Devolve a conexão manual, ou `None` se o arquivo não existe.

    Levanta `ConfigInvalid` se existir e estiver ilegível, for symlink ou tiver conteúdo inválido.
    """
    path = connection_path(home)
    with _lock:
        if not os.path.lexists(path):
            return None
        return _read(path)


def save(home: Path, config: ManualConfig) -> None:
    """Grava a conexão de forma atômica (temporário `.notislake-*` 0600 no mesmo diretório, fsync, replace)."""
    payload = (
        json.dumps(
            {
                "version": VERSION,
                "name": config.name,
                "endpoint": config.endpoint,
                "access_key": config.access_key,
                "secret_key": config.secret_key,
                "region": config.region,
                "timeout_s": config.timeout_s,
            },
            indent=2,
        )
        + "\n"
    )
    with _lock:
        home.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=home, prefix=".notislake-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                os.fchmod(tmp.fileno(), _FILE_MODE)
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, connection_path(home))
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def clear(home: Path) -> bool:
    """Remove a conexão manual (volta ao modo automático); devolve se havia arquivo."""
    with _lock:
        try:
            connection_path(home).unlink()
        except FileNotFoundError:
            return False
        return True
