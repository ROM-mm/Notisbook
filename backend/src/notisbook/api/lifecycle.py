"""Encerramento ordenado do backend: registro `run/backend.json` e rota de parada protegida por token.

O token do registro é distinto do token da UI e nunca é registrado em log. Quem lê `backend.json` (a próxima
versão do app, no mesmo home) pede o encerramento pela rota e espera o pid sair.
"""

import hmac
import json
import logging
import os
import secrets
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import HOST
from ..security import require_trusted_host

logger = logging.getLogger(__name__)

RUN_DIR = "run"
BACKEND_FILE = "backend.json"
SHUTDOWN_PATH = "/api/lifecycle/shutdown"
# stop() do MinIO (até ~15 s) + fallback dos containers (até 20 s) + prazo do uvicorn (5 s).
EXIT_WAIT_S = 60.0
REQUEST_TIMEOUT_S = 5.0
# Janela entre gravar o registro e o uvicorn escutar (ou loop momentaneamente travado) com pid vivo.
SILENT_PORT_GRACE_S = 10.0
_LOOPBACK = frozenset({"127.0.0.1", "::1"})
_POLL_S = 0.2


class PreviousInstanceError(Exception):
    """A instância anterior não pôde ser resolvida; a mensagem (em inglês) é para o usuário."""


class LifecycleControl:
    """Token de encerramento desta execução e o gatilho do encerramento ordenado (ligado ao servidor depois)."""

    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)
        self._request_exit: Callable[[], None] | None = None

    def bind(self, request_exit: Callable[[], None]) -> None:
        self._request_exit = request_exit

    def request_exit(self) -> None:
        if self._request_exit is not None:
            self._request_exit()


@dataclass(frozen=True)
class BackendRecord:
    pid: int
    port: int
    version: str
    token: str = ""


def _record_path(home: Path) -> Path:
    return home / RUN_DIR / BACKEND_FILE


def write_record(home: Path, record: BackendRecord) -> None:
    """Grava `backend.json` (0600) de forma atômica: temporário no mesmo diretório + `os.replace`."""
    run_dir = home / RUN_DIR
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(
        {"pid": record.pid, "port": record.port, "version": record.version, "token": record.token}
    ).encode()
    fd, tmp_name = tempfile.mkstemp(dir=run_dir, prefix=".backend-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_name, _record_path(home))
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def read_record(home: Path) -> BackendRecord | None:
    """Registro vivo no disco; ausente, ilegível ou malformado devolve None."""
    try:
        data: Any = json.loads(_record_path(home).read_text())
        return BackendRecord(
            pid=int(data["pid"]), port=int(data["port"]), version=str(data["version"]), token=str(data["token"])
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_record(home: Path, pid: int | None = None) -> None:
    """Remove `backend.json`; com `pid`, só se o registro ainda for desse processo."""
    if pid is not None:
        current = read_record(home)
        if current is not None and current.pid != pid:
            return
    try:
        _record_path(home).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("lifecycle: could not remove %s (%s)", _record_path(home), exc.strerror)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _probe(port: int) -> bool | None:
    """True: Notisbook na porta. False: algo responde HTTP sem `X-Notisbook`. None: nada responde."""
    request = urllib.request.Request(f"http://{HOST}:{port}/api/health")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
            return response.headers.get("X-Notisbook") is not None
    except urllib.error.HTTPError as exc:
        return exc.headers.get("X-Notisbook") is not None
    except (urllib.error.URLError, OSError):
        return None


def _probe_alive_pid(record: BackendRecord) -> bool | None:
    """Sonda a porta de um pid vivo repetindo enquanto muda; devolve o último resultado (None se persistir)."""
    deadline = time.monotonic() + SILENT_PORT_GRACE_S
    while True:
        result = _probe(record.port)
        if result is not None or time.monotonic() >= deadline or not _pid_alive(record.pid):
            return result
        time.sleep(_POLL_S)


def _request_shutdown(record: BackendRecord) -> None:
    request = urllib.request.Request(
        f"http://{HOST}:{record.port}{SHUTDOWN_PATH}",
        method="POST",
        headers={"Authorization": f"Bearer {record.token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S):
            pass
    except urllib.error.HTTPError as exc:
        raise PreviousInstanceError(
            f"Notisbook {record.version} (pid {record.pid}) refused the shutdown request (HTTP {exc.code}). "
            "Close it and run notisbook again."
        ) from None
    except (urllib.error.URLError, OSError) as exc:
        raise PreviousInstanceError(
            f"Could not ask Notisbook {record.version} (pid {record.pid}) to stop ({exc}). "
            "Close it and run notisbook again."
        ) from None


def _wait_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _pid_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_S)
    return True


def _live_instance(home: Path, own_pid: int | None = None) -> BackendRecord | None:
    """Registro de uma instância viva respondendo como Notisbook, ou None se não há (registro obsoleto é removido).

    Pid vivo com a porta muda após a espera: `PreviousInstanceError` sem apagar o registro.
    """
    record = read_record(home)
    if record is None:
        return None
    if record.pid == (own_pid if own_pid is not None else os.getpid()):
        return None
    if not _pid_alive(record.pid):
        remove_record(home, record.pid)
        return None
    probe = _probe_alive_pid(record)
    if probe is None:
        raise PreviousInstanceError(
            f"Notisbook {record.version} (pid {record.pid}) is running but not answering on port {record.port}. "
            "Close it and run notisbook again."
        )
    if not probe:
        remove_record(home, record.pid)
        return None
    return record


def _shutdown_and_wait(record: BackendRecord) -> None:
    _request_shutdown(record)
    if not _wait_exit(record.pid, EXIT_WAIT_S):
        raise PreviousInstanceError(
            f"Notisbook {record.version} (pid {record.pid}) did not exit within {int(EXIT_WAIT_S)} s. "
            "Close it and run notisbook again."
        )


def stop_previous_instance(home: Path, current_version: str, own_pid: int | None = None) -> None:
    """Resolve a instância registrada em `backend.json` antes de a atual subir.

    Registro obsoleto (pid morto, ou pid pertencente a outro serviço HTTP na porta) é removido. Versão diferente
    viva: pede o encerramento pela rota e espera o pid sair. Mesma versão viva ou falha: `PreviousInstanceError`.
    """
    record = _live_instance(home, own_pid)
    if record is None:
        return
    if record.version == current_version:
        raise PreviousInstanceError(
            f"Notisbook {record.version} is already running (pid {record.pid}, port {record.port}). "
            "Close it first, or use --port <other> with a different NOTISBOOK_HOME."
        )
    print(
        f"Notisbook: stopping the running Notisbook {record.version} (pid {record.pid}) to start {current_version}...",
        flush=True,
    )
    _shutdown_and_wait(record)
    print(f"Notisbook: Notisbook {record.version} stopped.", flush=True)


def stop_running_instance(home: Path) -> None:
    """Encerra a instância registrada em `backend.json` de qualquer versão, inclusive a atual.

    Sem registro ou com registro obsoleto não há o que parar (sem erro). Falha ao encerrar: `PreviousInstanceError`.
    """
    record = _live_instance(home)
    if record is None:
        print("Notisbook: no running instance found.", flush=True)
        return
    print(f"Notisbook: stopping the running Notisbook {record.version} (pid {record.pid})...", flush=True)
    _shutdown_and_wait(record)
    remove_record(home, record.pid)
    print(f"Notisbook: Notisbook {record.version} stopped.", flush=True)


def _control(request: Request) -> LifecycleControl:
    control: LifecycleControl | None = getattr(request.app.state, "lifecycle", None)
    if control is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return control


router = APIRouter(prefix="/api/lifecycle", dependencies=[Depends(require_trusted_host)])


@router.post("/shutdown", status_code=status.HTTP_202_ACCEPTED)
async def shutdown(request: Request) -> dict[str, str]:
    """Dispara o encerramento ordenado; só loopback e só com o token de `backend.json` (401 sem, 403 errado)."""
    control = _control(request)
    if request.client is None or request.client.host not in _LOOPBACK:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer ") or not header[7:].strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")
    if not hmac.compare_digest(header[7:].strip().encode(), control.token.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    control.request_exit()
    return {"status": "stopping"}
