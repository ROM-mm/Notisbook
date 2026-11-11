"""Preferências do operador em `<home>/preferences.json` (`{"version": 1, "notebooks_root": "/abs"}`).

Leitura tolerante: arquivo ausente, malformado ou de outra versão é ignorado com aviso.
Escrita atômica (arquivo temporário no mesmo diretório + `os.replace`), modo 0600.
Também concentra a validação da raiz dos notebooks, usada pela API e pelo start da CLI.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

FILENAME = "preferences.json"
VERSION = 1


def preferences_path(home: Path) -> Path:
    return home / FILENAME


def read_notebooks_root(home: Path) -> str | None:
    """Caminho salvo da raiz dos notebooks, ou None se ausente/inválido (sem validar o diretório)."""
    path = preferences_path(home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable preferences file %s: %s", path, exc)
        return None
    value = data.get("notebooks_root") if isinstance(data, dict) and data.get("version") == VERSION else None
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        logger.warning("Ignoring preferences file %s: unexpected content", path)
        return None
    return value


def stage_notebooks_root(home: Path, root: Path) -> Path:
    """Escreve a preferência num temporário (fsync, 0600) sem publicá-la; devolve o temporário.

    Separado do `commit` para que o commit (um `os.replace`) rode no event loop,
    atômico com a checagem final de sessões. Levanta OSError em falha.
    """
    payload = json.dumps({"version": VERSION, "notebooks_root": str(root)}, indent=2) + "\n"
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


def commit_notebooks_root(home: Path, staged: Path) -> None:
    """Publica o temporário de `stage_notebooks_root`; em falha o arquivo anterior fica intacto e o temporário é removido."""
    try:
        os.replace(staged, preferences_path(home))
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def write_notebooks_root(home: Path, root: Path) -> None:
    """Grava a raiz de forma atômica. Levanta OSError em falha (o arquivo anterior fica intacto)."""
    commit_notebooks_root(home, stage_notebooks_root(home, root))


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

    Bloqueia `/`, qualquer ancestral (ou o próprio) home do usuário e pasta de dados, e o interior desta.
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
    if resolved == data or data in resolved.parents:
        raise RootRejected(400, "The Notisbook data folder cannot be used as the notebooks folder")
    if any(p == resolved or p.is_relative_to(resolved) for p in (user_home, data)):
        raise RootRejected(400, "This folder cannot be used as the notebooks folder")
    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise RootRejected(403, "Folder is not readable and writable")
    return resolved
