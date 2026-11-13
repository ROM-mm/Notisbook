"""Preferências do operador em `<home>/preferences.json`.

Formato: `{"version": 1, "notebooks_root": "/abs", "samples_seeded": true}`; as duas chaves são opcionais
e chaves desconhecidas são preservadas na gravação. Leitura tolerante: arquivo malformado ou de outra
versão é ignorado com aviso. Escrita atômica (temporário no mesmo diretório + `os.replace`), modo 0600,
sempre mesclada ao conteúdo atual. Também concentra a validação da raiz dos notebooks (API e CLI).
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from .config import default_root

logger = logging.getLogger(__name__)

FILENAME = "preferences.json"
VERSION = 1


def preferences_path(home: Path) -> Path:
    return home / FILENAME


def _read_raw(home: Path) -> dict[str, Any] | None:
    """Conteúdo do arquivo quando é um objeto JSON `version == 1`; None se ausente, ilegível ou de outra versão."""
    path = preferences_path(home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable preferences file %s: %s", path, exc)
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        logger.warning("Ignoring preferences file %s: unexpected content", path)
        return None
    return data


def read_notebooks_root(home: Path) -> str | None:
    """Caminho salvo da raiz dos notebooks, ou None se ausente/inválido (sem validar o diretório)."""
    data = _read_raw(home)
    if data is None or "notebooks_root" not in data:
        return None
    value = data["notebooks_root"]
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        logger.warning("Ignoring preferences file %s: unexpected content", preferences_path(home))
        return None
    return value


def _stage(home: Path, updates: dict[str, Any]) -> Path:
    """Mescla `updates` ao conteúdo atual e grava num temporário (fsync, 0600); devolve o temporário."""
    merged = {**(_read_raw(home) or {}), "version": VERSION, **updates}
    payload = json.dumps(merged, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=home, prefix=".preferences-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, 0o600)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return Path(tmp_name)


def stage_notebooks_root(home: Path, root: Path, *, samples_seeded: bool = False) -> Path:
    """Escreve a preferência num temporário sem publicá-la; devolve o temporário.

    Separado do `commit` para que o commit (um `os.replace`) rode no event loop,
    atômico com a checagem final de sessões. Preserva as demais chaves do arquivo atual.
    `samples_seeded=True` também grava o marcador. Levanta OSError em falha.
    """
    updates: dict[str, Any] = {"notebooks_root": str(root)}
    if samples_seeded:
        updates["samples_seeded"] = True
    return _stage(home, updates)


def commit_notebooks_root(home: Path, staged: Path) -> None:
    """Publica o temporário de `stage_notebooks_root`; em falha o arquivo anterior fica intacto e o temporário é removido."""
    try:
        os.replace(staged, preferences_path(home))
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def write_notebooks_root(home: Path, root: Path, *, samples_seeded: bool = False) -> None:
    """Grava a raiz de forma atômica. Levanta OSError em falha (o arquivo anterior fica intacto)."""
    commit_notebooks_root(home, stage_notebooks_root(home, root, samples_seeded=samples_seeded))


def mark_samples_seeded(home: Path) -> None:
    """Grava o marcador `samples_seeded` (atômico, 0600), preservando as demais chaves. Levanta OSError em falha."""
    commit_notebooks_root(home, _stage(home, {"samples_seeded": True}))


class RootRejected(Exception):
    """Raiz de notebooks recusada; carrega o status HTTP e a mensagem para o cliente."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def protected_paths(data_home: Path) -> tuple[Path, ...]:
    """Home do usuário e pasta de dados do Notisbook, resolvidos: nem eles nem seus ancestrais viram raiz ou são apagados."""
    return (Path.home().resolve(), data_home.resolve())


def validate_notebooks_root(raw: str, data_home: Path) -> Path:
    """Caminho absoluto, existente, diretório acessível e fora das raízes proibidas; devolve o caminho resolvido.

    Bloqueia `/`, qualquer ancestral (ou o próprio) home do usuário e pasta de dados, e o interior desta,
    exceto `<dados>/notebooks` (comparação exata, com caixa) e seus descendentes.
    I/O bloqueante: chame fora do event loop. Levanta `RootRejected`.
    """
    if "\x00" in raw or not raw.startswith("/"):
        raise RootRejected(400, "Path must be absolute")
    try:
        resolved = Path(raw).resolve(strict=True)
    except FileNotFoundError as exc:
        raise RootRejected(404, "Folder not found") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise RootRejected(400, "Invalid path") from exc
    if not resolved.is_dir():
        raise RootRejected(400, "Not a directory")
    user_home, data = protected_paths(data_home)
    managed = default_root(data)
    in_managed = resolved == managed or managed in resolved.parents
    if not in_managed and (resolved == data or data in resolved.parents):
        raise RootRejected(400, "The Notisbook data folder cannot be used as the notebooks folder")
    if any(p == resolved or p.is_relative_to(resolved) for p in (user_home, data)):
        raise RootRejected(400, "This folder cannot be used as the notebooks folder")
    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise RootRejected(403, "Folder is not readable and writable")
    return resolved
