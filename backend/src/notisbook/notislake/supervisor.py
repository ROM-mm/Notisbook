"""Supervisor do MinIO local (notislake): sobe, vigia, reinicia e para o processo.

Um `NOTISBOOK_HOME` tem um único supervisor: `flock` exclusivo em `<home>/minio/run/notislake.lock`
(fd não herdável) vale até em SIGKILL. O MinIO roda em sessão própria, com a credencial só no `env`
do `Popen` (nunca em argv nem em `os.environ`). Um órfão de execução anterior é achado pelo pidfile
(pid + create_time) e por varredura psutil, e encerrado antes da nova subida.

`start()` é síncrono e levanta `StartError`; depois disso uma thread monitora o processo e o reinicia
com backoff. Mensagens ao operador vão para stderr; `snapshot()` só expõe códigos e textos fixos.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import psutil

from ..config import default_home
from . import binary
from .bootstrap import READY_TIMEOUT_S, BootstrapError, ensure_layout, wait_ready
from .credentials import Credentials, CredentialsError, load_or_create
from .ports import LOOPBACK, is_free, pick_free_ports

STOP_GRACE_S = 10.0
KILL_WAIT_S = 5.0
BACKOFF_S = (1.0, 2.0, 4.0, 8.0, 16.0)
STABLE_AFTER_S = 60.0
PORT_ATTEMPTS = 3
LOG_ROTATE_BYTES = 10 * 1024 * 1024
_POLL_S = 0.5
_CREATE_TIME_TOLERANCE_S = 1.0
_DIR_MODE = 0o700
_FILE_MODE = 0o600


class State(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    FAILED = "failed"
    STOPPING = "stopping"


# Textos fixos expostos pela API; detalhes (caminhos, causas) vão só para o stderr.
_MESSAGES = {
    "locked": "A pasta de dados já está em uso por outro Notisbook.",
    "binary_missing": "MinIO indisponível: binário ausente ou não instalado.",
    "binary_invalid": "MinIO indisponível: o pacote do binário foi recusado na verificação.",
    "unsupported_platform": "MinIO indisponível: sistema ou arquitetura sem binário.",
    "permission": "Sem permissão para usar a pasta de dados do MinIO.",
    "io_error": "Falha de disco ao preparar a pasta do MinIO.",
    "credentials": "A credencial do MinIO está ilegível ou inválida.",
    "port_conflict": "Não foi possível obter portas livres para o MinIO.",
    "start_failed": "O MinIO encerrou ao subir.",
    "not_ready": "O MinIO não ficou pronto no prazo.",
    "layout": "Não foi possível criar o bucket e os prefixos do notislake.",
    "orphan": "Não foi possível encerrar um MinIO órfão de execução anterior.",
    "crash_loop": "O MinIO encerrou repetidamente e deixou de ser reiniciado.",
    "internal": "Erro interno ao supervisionar o MinIO.",
}


class StartError(Exception):
    """Falha de subida; `code` é categórico e a mensagem (detalhada) nunca contém a senha."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        super().__init__(detail or _MESSAGES[code])


class _StopRequested(Exception):
    """Interna: `stop()` foi pedido enquanto a thread trabalhava."""


@dataclass(frozen=True)
class SupervisorError:
    code: str
    message: str


@dataclass(frozen=True)
class Snapshot:
    """Foto imutável do estado; as portas só existem em `running`."""

    state: State
    since: datetime
    restarts: int
    api_port: int | None
    console_port: int | None
    error: SupervisorError | None


@dataclass(frozen=True)
class LocalConnection:
    endpoint: str
    access_key: str
    secret_key: str = field(repr=False)

    def __repr__(self) -> str:
        return f"LocalConnection(endpoint={self.endpoint!r}, access_key={self.access_key!r}, secret_key='***')"

    __str__ = __repr__


@dataclass(frozen=True)
class _Paths:
    root: Path

    @property
    def run(self) -> Path:
        return self.root / "run"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def lock(self) -> Path:
        return self.run / "notislake.lock"

    @property
    def pidfile(self) -> Path:
        return self.run / "minio.pid"

    @property
    def log(self) -> Path:
        return self.logs / "minio.log"


class LockBusyError(Exception):
    """O flock da pasta de dados está com outro processo."""


def lock_path(home: Path) -> Path:
    """Arquivo do flock que garante um único backend por `NOTISBOOK_HOME`."""
    return _Paths(home / "minio").lock


def acquire_flock(path: Path) -> int:
    """Abre `path` e toma o flock exclusivo sem bloquear; devolve o fd (não herdável).

    `LockBusyError` se outro processo o detém; falha ao abrir sobe como `OSError`.
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, _FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise LockBusyError from None
    return fd


def _say(message: str) -> None:
    print(f"Notisbook: {message}", file=sys.stderr, flush=True)


def _now() -> datetime:
    return datetime.now(UTC)


def _child_env(credentials: Credentials) -> dict[str, str]:
    """Ambiente do MinIO: sem `MINIO_*`/`MC_*` herdados; a credencial existe só aqui."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("MINIO_", "MC_"))}
    env["MINIO_ROOT_USER"] = credentials.user
    env["MINIO_ROOT_PASSWORD"] = credentials.password
    return env


def _terminate(proc: subprocess.Popen) -> None:
    """SIGTERM, espera `STOP_GRACE_S` e então SIGKILL; não faz nada se já terminou."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(STOP_GRACE_S)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            pass


def _looks_like_minio(cmdline: list[str]) -> bool:
    return bool(cmdline) and os.path.basename(cmdline[0]).startswith("minio")


class NotislakeSupervisor:
    """Ciclo de vida do MinIO local; thread-safe. `home` default: `default_home()`."""

    def __init__(self, home: Path | None = None) -> None:
        self._home = home if home is not None else default_home()
        self._paths = _Paths(self._home / "minio")
        self._lock = threading.RLock()
        self._stop_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._state = State.STOPPED
        self._since = _now()
        self._restarts = 0
        self._ports: tuple[int, int] | None = None
        self._last_ports: tuple[int, int] | None = None
        self._error: SupervisorError | None = None
        self._credentials: Credentials | None = None
        self._minio: Path | None = None
        self._proc: subprocess.Popen | None = None
        self._started_at = 0.0
        self._lock_fd: int | None = None
        self._thread: threading.Thread | None = None

    def __repr__(self) -> str:
        with self._lock:
            return f"NotislakeSupervisor(state={self._state.value!r}, api_port={self._ports[0] if self._ports else None}, restarts={self._restarts})"

    @property
    def home(self) -> Path:
        return self._home


    def start(self) -> None:
        """Sobe o MinIO e só retorna em `running`; levanta `StartError` (estado fica `failed`).

        Exige `stopped`. Após falha, o flock continua retido até `stop()` (ou `retry()`).
        """
        with self._lock:
            if self._state is not State.STOPPED:
                raise RuntimeError(f"supervisor já iniciado (estado {self._state.value})")
            self._stop_event.clear()
            self._transition(State.STARTING)
        try:
            proc, ports = self._bring_up()
            self._enter_running(proc, ports)
        except StartError as exc:
            self._fail(exc)
            raise
        except _StopRequested:
            exc = StartError("start_failed", "subida interrompida por stop()")
            self._fail(exc)
            raise exc from None
        except Exception as exc:  # noqa: BLE001
            self._fail(StartError("internal"))
            raise StartError("internal", f"erro interno ao subir o MinIO ({type(exc).__name__})") from None
        self._spawn_thread(self._monitor, proc)

    def stop(self) -> None:
        """Para o MinIO (SIGTERM, 10 s, SIGKILL), remove o pidfile e solta o flock; idempotente."""
        with self._stop_lock:
            with self._lock:
                if self._state is State.STOPPED:
                    return
                self._stop_event.set()
                self._force_state(State.STOPPING)
                thread = self._thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(STOP_GRACE_S + KILL_WAIT_S + 5)
            with self._lock:
                proc = self._proc
            if proc is not None:
                _terminate(proc)
            self._remove_pidfile()
            self._release_lock()
            with self._lock:
                self._proc = None
                self._thread = None
                self._force_state(State.STOPPED)

    def snapshot(self) -> Snapshot:
        with self._lock:
            ports = self._ports
            return Snapshot(
                state=self._state,
                since=self._since,
                restarts=self._restarts,
                api_port=ports[0] if ports else None,
                console_port=ports[1] if ports else None,
                error=self._error,
            )

    def connection(self) -> LocalConnection | None:
        """Endpoint e credenciais do MinIO local; `None` fora de `running`."""
        with self._lock:
            if self._state is not State.RUNNING or self._ports is None or self._credentials is None:
                return None
            return LocalConnection(
                endpoint=f"http://{LOOPBACK}:{self._ports[0]}",
                access_key=self._credentials.user,
                secret_key=self._credentials.password,
            )

    def retry(self) -> bool:
        """Sai de `failed` subindo na thread do monitor; `False` (sem efeito) em qualquer outro estado."""
        with self._lock:
            if self._state is not State.FAILED or self._stop_event.is_set():
                return False
            self._transition(State.STARTING)
        self._spawn_thread(self._retry_main)
        return True


    def _force_state(self, state: State) -> None:
        with self._lock:
            self._state = state
            self._since = _now()
            self._error = None
            self._ports = None

    def _transition(self, state: State, error: SupervisorError | None = None) -> bool:
        """Muda de estado, salvo se `stop()` já foi pedido (então devolve False e nada muda)."""
        with self._lock:
            if self._stop_event.is_set():
                return False
            self._force_state(state)
            self._error = error
            return True

    def _enter_running(self, proc: subprocess.Popen, ports: tuple[int, int]) -> None:
        with self._lock:
            if not self._transition(State.RUNNING):
                raise _StopRequested
            self._ports = self._last_ports = ports
            self._started_at = time.monotonic()
            self._proc = proc

    def _fail(self, exc: StartError) -> None:
        self._transition(State.FAILED, SupervisorError(exc.code, _MESSAGES[exc.code]))

    def _spawn_thread(self, target, *args) -> None:
        thread = threading.Thread(target=target, args=args, name="notislake-monitor", daemon=True)
        with self._lock:
            self._thread = thread
        thread.start()


    def _bring_up(self) -> tuple[subprocess.Popen, tuple[int, int]]:
        """Prepara pastas, trava, encerra órfãos, instala o binário e sobe o MinIO até a prontidão."""
        self._prepare_dirs()
        self._acquire_lock()
        self._reap_orphans()
        self._credentials = self._load_credentials()
        self._minio = self._install()
        return self._launch(None)

    def _prepare_dirs(self) -> None:
        paths = self._paths
        try:
            for folder in (paths.run, paths.data, paths.logs):
                folder.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        except PermissionError as exc:
            raise StartError("permission", f"sem permissão para criar {exc.filename} ({exc.strerror})") from None
        except OSError as exc:
            raise StartError("io_error", f"falha ao preparar {exc.filename} ({exc.strerror})") from None
        if not os.access(paths.data, os.R_OK | os.W_OK | os.X_OK):
            raise StartError("permission", f"sem permissão de leitura/escrita em {paths.data}")

    def _acquire_lock(self) -> None:
        if self._lock_fd is not None:
            return
        try:
            self._lock_fd = acquire_flock(self._paths.lock)
        except LockBusyError:
            raise StartError(
                "locked", f"a pasta de dados {self._home} já está em uso por outro Notisbook; use outro NOTISBOOK_HOME"
            ) from None
        except OSError as exc:
            raise StartError("io_error", f"não foi possível abrir {self._paths.lock} ({exc.strerror})") from None

    def _release_lock(self) -> None:
        fd, self._lock_fd = self._lock_fd, None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _load_credentials(self) -> Credentials:
        try:
            return load_or_create(self._home)
        except CredentialsError as exc:
            raise StartError("credentials", f"credencial do MinIO inválida: {exc}") from None
        except OSError as exc:
            raise StartError("io_error", f"falha ao preparar a credencial ({exc.strerror})") from None

    def _install(self) -> Path:
        try:
            return binary.install(self._home).minio
        except binary.BinaryNotInstalledError as exc:
            raise StartError("binary_missing", f"MinIO indisponível: binário ausente. {exc}") from None
        except binary.BinaryIntegrityError as exc:
            raise StartError("binary_invalid", f"MinIO indisponível: pacote recusado. {exc}") from None
        except binary.UnsupportedPlatformError as exc:
            raise StartError("unsupported_platform", f"MinIO indisponível: {exc}") from None
        except binary.BinaryError as exc:
            code = "permission" if isinstance(exc.__cause__, PermissionError) else "io_error"
            raise StartError(code, f"MinIO indisponível: {exc}") from None
        except OSError as exc:
            raise StartError("io_error", f"falha ao instalar o binário ({exc.strerror})") from None


    def _reap_orphans(self) -> None:
        victims: dict[int, psutil.Process] = {}
        pid_proc = self._pidfile_process()
        if pid_proc is not None:
            victims[pid_proc.pid] = pid_proc
        for proc in self._sweep():
            victims[proc.pid] = proc
        for proc in victims.values():
            self._kill_orphan(proc)
        self._remove_pidfile()

    def _pidfile_process(self) -> psutil.Process | None:
        try:
            data = json.loads(self._paths.pidfile.read_text(encoding="utf-8"))
            pid, created = int(data["pid"]), float(data["create_time"])
            proc = psutil.Process(pid)
            if abs(proc.create_time() - created) > _CREATE_TIME_TOLERANCE_S:
                return None  # pid reutilizado por outro processo
            return proc if _looks_like_minio(proc.cmdline()) else None
        except (OSError, ValueError, TypeError, KeyError, psutil.Error):
            return None

    def _sweep(self) -> Iterator[psutil.Process]:
        """Processos `minio server` que usam o `data/` deste home (cobre pidfile perdido)."""
        data = str(self._paths.data)
        real = os.path.realpath(data)
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmd = proc.info.get("cmdline") or []
            if proc.pid == os.getpid() or "server" not in cmd or not _looks_like_minio(cmd):
                continue
            if any(a == data or (a.startswith("/") and os.path.realpath(a) == real) for a in cmd[1:]):
                yield proc

    def _kill_orphan(self, proc: psutil.Process) -> None:
        _say(f"encerrando MinIO órfão (pid {proc.pid}) de uma execução anterior.")
        try:
            proc.terminate()
            _, alive = psutil.wait_procs([proc], timeout=STOP_GRACE_S)
            if alive:
                proc.kill()
                _, alive = psutil.wait_procs([proc], timeout=KILL_WAIT_S)
        except psutil.NoSuchProcess:
            return
        except psutil.AccessDenied:
            alive = [proc]
        if alive:
            raise StartError("orphan", f"não foi possível encerrar o MinIO órfão (pid {proc.pid})")


    def _launch(self, preferred: tuple[int, int] | None) -> tuple[subprocess.Popen, tuple[int, int]]:
        """Sobe o processo e espera a prontidão; repete com portas novas se alguém tomou as escolhidas."""
        for attempt in range(PORT_ATTEMPTS):
            ports = self._choose_ports(preferred if attempt == 0 else None)
            proc = self._spawn(ports)
            ok = False
            try:
                alive = lambda p=proc: p.poll() is None and not self._stop_event.is_set()
                if wait_ready(ports[0], READY_TIMEOUT_S, is_alive=alive):
                    self._ensure_layout(ports[0])
                    ok = True
                    return proc, ports
                self._explain_not_ready(proc, ports)
            finally:
                if not ok:
                    _terminate(proc)
                    self._remove_pidfile()
            _say(f"porta do MinIO ocupada ({ports[0]}/{ports[1]}); tentando outras ({attempt + 1}/{PORT_ATTEMPTS}).")
        raise StartError("port_conflict")

    @staticmethod
    def _choose_ports(preferred: tuple[int, int] | None) -> tuple[int, int]:
        if preferred is not None and all(is_free(p) for p in preferred):
            return preferred
        api, console = pick_free_ports(2)
        return api, console

    def _ensure_layout(self, api_port: int) -> None:
        assert self._credentials is not None
        try:
            ensure_layout(api_port, self._credentials)
        except BootstrapError as exc:
            raise StartError("layout", str(exc)) from None

    def _explain_not_ready(self, proc: subprocess.Popen, ports: tuple[int, int]) -> None:
        """Volta normalmente só em conflito de porta; nos demais casos levanta."""
        if self._stop_event.is_set():
            raise _StopRequested
        if proc.poll() is None:
            raise StartError("not_ready", f"o MinIO não respondeu em {READY_TIMEOUT_S:g}s; veja {self._paths.log}")
        if any(not is_free(p) for p in ports):
            return
        raise StartError("start_failed", f"o MinIO encerrou ao subir (código {proc.returncode}); veja {self._paths.log}")

    def _rotate_log(self) -> None:
        log = self._paths.log
        try:
            if log.stat().st_size > LOG_ROTATE_BYTES:
                os.replace(log, log.with_name(log.name + ".1"))
        except OSError:
            pass  # rotação é só higiene; sem ela o log apenas cresce

    def _spawn(self, ports: tuple[int, int]) -> subprocess.Popen:
        if self._stop_event.is_set():
            raise _StopRequested
        assert self._credentials is not None and self._minio is not None
        argv = [
            str(self._minio), "server", str(self._paths.data),
            "--address", f"{LOOPBACK}:{ports[0]}",
            "--console-address", f"{LOOPBACK}:{ports[1]}",
            "--quiet",
        ]  # fmt: skip
        self._rotate_log()
        try:
            log_fd = os.open(self._paths.log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC, _FILE_MODE)
        except OSError as exc:
            raise StartError("io_error", f"não foi possível abrir {self._paths.log} ({exc.strerror})") from None
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=log_fd,
                env=_child_env(self._credentials),
                close_fds=True,
                start_new_session=True,
            )
        except PermissionError as exc:
            raise StartError("permission", f"sem permissão para executar {self._minio} ({exc.strerror})") from None
        except OSError as exc:
            raise StartError("start_failed", f"não foi possível executar {self._minio} ({exc.strerror})") from None
        finally:
            os.close(log_fd)
        with self._lock:
            self._proc = proc
        self._write_pidfile(proc, ports)
        return proc

    def _write_pidfile(self, proc: subprocess.Popen, ports: tuple[int, int]) -> None:
        try:
            created = psutil.Process(proc.pid).create_time()
            payload = json.dumps({"pid": proc.pid, "create_time": created, "api_port": ports[0], "console_port": ports[1]})
            fd, tmp = tempfile.mkstemp(dir=self._paths.run, prefix=".minio-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, self._paths.pidfile)
        except (OSError, psutil.Error) as exc:
            _say(f"não foi possível gravar o pidfile do MinIO ({type(exc).__name__}); órfãos serão achados por varredura.")

    def _remove_pidfile(self) -> None:
        """Remove o pidfile só se esta instância detém o flock; sem ele o arquivo é de outro Notisbook."""
        if self._lock_fd is None:
            return
        self._paths.pidfile.unlink(missing_ok=True)


    def _retry_main(self) -> None:
        try:
            proc, ports = self._bring_up()
            self._enter_running(proc, ports)
        except _StopRequested:
            return
        except StartError as exc:
            _say(f"nova tentativa do MinIO falhou: {exc}")
            self._fail(exc)
            return
        except Exception as exc:  # noqa: BLE001
            _say(f"erro interno ao tentar subir o MinIO ({type(exc).__name__}).")
            self._fail(StartError("internal"))
            return
        _say(f"MinIO (notislake) em execução na porta {ports[0]}.")
        self._monitor(proc)

    def _monitor(self, proc: subprocess.Popen) -> None:
        try:
            self._watch(proc)
        except _StopRequested:
            return
        except Exception as exc:  # noqa: BLE001
            _say(f"erro interno no monitor do MinIO ({type(exc).__name__}).")
            self._fail(StartError("internal"))

    def _wait_exit(self, proc: subprocess.Popen) -> bool:
        """True quando o processo morreu; False se `stop()` foi pedido antes."""
        while proc.poll() is None:
            if self._stop_event.wait(_POLL_S):
                return False
        return not self._stop_event.is_set()

    def _watch(self, proc: subprocess.Popen | None) -> None:
        consecutive = 0
        code: int | None = None
        while True:
            if proc is not None:
                if not self._wait_exit(proc):
                    return
                if time.monotonic() - self._started_at >= STABLE_AFTER_S:
                    consecutive = 0
                self._remove_pidfile()
                code = proc.returncode
            if consecutive >= len(BACKOFF_S):
                _say(f"MinIO (notislake) falhou após {len(BACKOFF_S)} reinícios; veja {self._paths.log}.")
                self._fail(StartError("crash_loop"))
                return
            delay = BACKOFF_S[consecutive]
            consecutive += 1
            if not self._begin_restart(code, delay, consecutive):
                return
            if self._stop_event.wait(delay):
                return
            proc = self._respawn()

    def _begin_restart(self, code: int | None, delay: float, attempt: int) -> bool:
        with self._lock:
            if not self._transition(State.RESTARTING):
                return False
            self._restarts += 1
        _say(f"MinIO (notislake) encerrou (código {code}); reiniciando em {delay:g}s ({attempt}/{len(BACKOFF_S)}).")
        return True

    def _respawn(self) -> subprocess.Popen | None:
        """Sobe de novo (mesmas portas se livres); `None` conta como mais uma morte no backoff."""
        try:
            proc, ports = self._launch(self._last_ports)
        except StartError as exc:
            _say(f"MinIO (notislake) não voltou: {exc}")
            return None
        self._enter_running(proc, ports)
        _say(f"MinIO (notislake) voltou a responder na porta {ports[0]}.")
        return proc
