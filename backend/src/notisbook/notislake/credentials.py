"""Credencial root do MinIO local, gerada uma vez e guardada em `<home>/minio/credentials.json` (0600).

A senha nunca aparece em `repr` nem nas mensagens de erro. A criação é atômica: o arquivo só
fica visível já completo e com permissão 0600, e dois processos concorrentes convergem para o mesmo conteúdo.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

VERSION = 1
_USER_PREFIX = "notisbook-"
_USER_MIN, _USER_MAX = 3, 20
_PASSWORD_MIN = 8
_FILE_MODE = 0o600


class CredentialsError(Exception):
    """Credencial ilegível ou inválida; a mensagem nunca contém a senha."""


@dataclass(frozen=True)
class Credentials:
    user: str
    password: str = field(repr=False)

    def __repr__(self) -> str:
        return f"Credentials(user={self.user!r}, password='***')"

    __str__ = __repr__


def credentials_path(home: Path) -> Path:
    return home / "minio" / "credentials.json"


def _validate(user: object, password: object) -> Credentials:
    if not isinstance(user, str) or not _USER_MIN <= len(user) <= _USER_MAX:
        raise CredentialsError(f"MinIO user must have {_USER_MIN}-{_USER_MAX} characters")
    if not isinstance(password, str) or len(password) < _PASSWORD_MIN:
        raise CredentialsError(f"MinIO password must have at least {_PASSWORD_MIN} characters")
    return Credentials(user=user, password=password)


def _read(path: Path) -> Credentials:
    """Lê e valida o arquivo (sem seguir symlink); corrige permissão aberta com aviso em stderr."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise CredentialsError(f"cannot read {path} ({exc.strerror})") from None
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise CredentialsError(f"{path} is not a regular file")
        if stat.S_IMODE(info.st_mode) & 0o077:
            os.fchmod(handle.fileno(), _FILE_MODE)
            print(f"Notisbook: permissões de {path} estavam abertas; ajustadas para 0600.", file=sys.stderr)
        try:
            data = json.load(handle)
        except (ValueError, UnicodeDecodeError):
            raise CredentialsError(f"{path} is not valid JSON") from None
    if not isinstance(data, dict):
        raise CredentialsError(f"{path} has unexpected content")
    return _validate(data.get("user"), data.get("password"))


def _create(path: Path) -> None:
    """Grava a credencial nova num temporário 0600 e a publica com `os.link` (falha se já existir)."""
    creds = Credentials(user=f"{_USER_PREFIX}{secrets.token_hex(2)}", password=secrets.token_urlsafe(18))
    payload = json.dumps({"version": VERSION, "user": creds.user, "password": creds.password}, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".credentials-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            os.fchmod(tmp.fileno(), _FILE_MODE)
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.link(tmp_name, path)
        except FileExistsError:
            pass  # outro processo publicou primeiro; _read devolve o dele
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def load_or_create(home: Path) -> Credentials:
    """Devolve a credencial de `<home>/minio/credentials.json`, criando-a na primeira chamada.

    Levanta `CredentialsError` se o arquivo existir mas estiver ilegível ou inválido.
    """
    path = credentials_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(path):
        _create(path)
    return _read(path)
