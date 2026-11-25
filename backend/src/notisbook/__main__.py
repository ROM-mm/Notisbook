"""CLI entry point: `notisbook [--port N] [--root DIR] [--no-browser]`, `notisbook update [--version X.Y.Z]`, `notisbook uninstall [--yes]`, `notisbook --install-default-runtimes`, `notisbook --runtimes-summary` and `notisbook --seed-samples [--if-missing]`."""

import argparse
import dataclasses
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from uvicorn.config import STARTUP_FAILURE

from . import __version__
from .api import lifecycle
from .app import create_app
from .catalog.store import ensure_catalog_db
from .config import (
    DEFAULT_PORT,
    HOST,
    Settings,
    default_home,
    ensure_home,
)
from .maintenance import (
    runtimes_bootstrap,
    runtimes_summary,
    samples_seed,
    uninstall,
    update,
)
from .notislake import binary
from .notislake.supervisor import NotislakeSupervisor, StartError
from .onboarding import run_onboarding, saved_or_default_root
from .runtimes.docker import catalog as docker_catalog
from .runtimes.docker import cli as docker_cli
from .runtimes.docker.service import inspect_container

# Prazo para a aba/WebSockets abertos soltarem o servidor: sem ele o 1º Ctrl+C espera sem limite e o 2º
# (saída forçada) pula o lifespan, onde os containers são parados.
GRACEFUL_SHUTDOWN_S = 5
# Prazo total do fallback que para os containers do app depois que o servidor sai.
FALLBACK_STOP_BUDGET_S = 20.0
FALLBACK_STOP_GRACE_S = 10
# Prazo do `minio --version` na checagem do pacote.
CHECK_MINIO_TIMEOUT_S = 30


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="notisbook")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--check-notislake",
        action="store_true",
        help="install the bundled MinIO into a temporary home, verify it and exit (starts no server)",
    )
    parser.add_argument(
        "--stop-running",
        action="store_true",
        help="stop the running Notisbook registered in the data folder, whatever its version, and exit (starts no server)",
    )
    parser.add_argument(
        "--install-default-runtimes",
        action="store_true",
        help="install the default Spark and DuckDB runtimes and exit (starts no server)",
    )
    parser.add_argument(
        "--runtimes-summary",
        action="store_true",
        help="list the managed Spark and DuckDB runtimes and exit (starts no server)",
    )
    parser.add_argument(
        "--seed-samples",
        action="store_true",
        help="copy the bundled sample notebooks missing from the active notebooks folder and exit (starts no server)",
    )
    parser.add_argument(
        "--if-missing",
        action="store_true",
        help="with --seed-samples: do nothing if the notebooks folder already exists",
    )
    commands = parser.add_subparsers(dest="command")
    update_cmd = commands.add_parser("update", help="update Notisbook to the latest release (or --version)")
    update_cmd.add_argument("--version", dest="target_version", metavar="X.Y.Z", help="release to install (default: latest)")
    uninstall_cmd = commands.add_parser("uninstall", help="remove Notisbook and keep your data folder")
    uninstall_cmd.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)
    actions = [
        flag
        for flag, active in (
            ("--check-notislake", args.check_notislake),
            ("--stop-running", args.stop_running),
            ("--install-default-runtimes", args.install_default_runtimes),
            ("--runtimes-summary", args.runtimes_summary),
            ("--seed-samples", args.seed_samples),
        )
        if active
    ]
    if len(actions) > 1:
        parser.error(f"{' and '.join(actions[:2])} cannot be combined: each one is a separate action")
    if args.command and _server_flags_set(args):
        parser.error(f"server options cannot be combined with the '{args.command}' command")
    if args.install_default_runtimes and _serve_options_set(args):
        parser.error("--install-default-runtimes cannot be combined with server options")
    if args.runtimes_summary and _serve_options_set(args):
        parser.error("--runtimes-summary cannot be combined with server options")
    if args.seed_samples and _serve_options_set(args):
        parser.error("--seed-samples cannot be combined with server options")
    if args.if_missing and not args.seed_samples:
        parser.error("--if-missing requires --seed-samples")
    if args.port is None:
        args.port = DEFAULT_PORT
    return args


def _serve_options_set(args: argparse.Namespace) -> bool:
    """True se alguma opção que configura o servidor (--port, --root, --no-browser) foi passada."""
    return args.port is not None or args.root is not None or args.no_browser


def _server_flags_set(args: argparse.Namespace) -> bool:
    """True se alguma flag do modo servidor foi passada (argparse aceitaria `--port 1 update` em silêncio)."""
    return (
        _serve_options_set(args)
        or args.check_notislake
        or args.stop_running
        or args.install_default_runtimes
        or args.runtimes_summary
        or args.seed_samples
        or args.if_missing
    )


def _check_notislake() -> int:
    """Instala o pacote MinIO num home temporário, confere o sha e roda `minio --version`; 0 = válido.

    Nunca toca no home real nem sobe servidor. As mensagens saem em inglês (stderr em falha).
    """
    try:
        with tempfile.TemporaryDirectory(prefix="notisbook-check-") as tmp:
            installed = binary.install(Path(tmp))
            result = subprocess.run(
                [str(installed.minio), "--version"],
                capture_output=True,
                text=True,
                timeout=CHECK_MINIO_TIMEOUT_S,
                check=False,
            )
    except binary.BinaryNotInstalledError:
        print(
            f"Notisbook: notislake check failed: package not found; {binary.DIST_ENV} is unset or points to a missing "
            f"path, and the default directory {binary.default_dist_dir()} does not exist.",
            file=sys.stderr,
        )
        return 1
    except binary.BinaryIntegrityError:
        print("Notisbook: notislake check failed: the package does not match the checksums in the manifest.", file=sys.stderr)
        return 1
    except binary.UnsupportedPlatformError:
        print("Notisbook: notislake check failed: no MinIO build for this platform.", file=sys.stderr)
        return 1
    except binary.BinaryError as exc:
        print(f"Notisbook: notislake check failed: could not install the package ({exc}).", file=sys.stderr)
        return 1
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Notisbook: notislake check failed: could not run minio --version ({exc}).", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"Notisbook: notislake check failed: minio --version exited with {result.returncode}.", file=sys.stderr)
        return 1
    first_line = (result.stdout.strip().splitlines() or ["(no output)"])[0]
    print(f"Notisbook: notislake OK (MinIO {installed.tag}: {first_line})")
    return 0


def _stop_running() -> int:
    """Encerra a instância registrada no home de dados; 0 = parou ou não havia nada rodando, 1 = falhou."""
    try:
        lifecycle.stop_running_instance(default_home())
    except lifecycle.PreviousInstanceError as exc:
        print(f"Notisbook: {exc}", file=sys.stderr)
        return 1
    return 0


def _resolve_root(cli_root: Path | None, home: Path) -> tuple[Path, str, bool]:
    """Raiz inicial e sua origem: `--root` (trava a UI) > preferência salva > `default_root(home)`.

    A preferência salva nunca é criada aqui: se for inválida (mesma validação da API), cai no default com aviso.
    """
    if cli_root is not None:
        return cli_root.expanduser().resolve(), "cli", True
    root, source = saved_or_default_root(home)
    return root, source, False


def _stop_owned_containers() -> None:
    """Fallback síncrono pós-servidor: para (nunca remove) containers do catálogo com label de dono e ainda rodando.

    Idempotente: o lifespan normalmente já parou tudo. SIGINT é ignorado aqui (prazo total limitado) para
    um Ctrl+C a mais não abortar o `docker stop`.
    """
    deadline = time.monotonic() + FALLBACK_STOP_BUDGET_S
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        if docker_cli.docker_binary() is None or not docker_cli.is_available(timeout=min(5.0, FALLBACK_STOP_BUDGET_S)):
            print("Notisbook: Docker indisponível; containers dos runtimes não foram verificados.", file=sys.stderr)
            return
        for runtime in docker_catalog.CATALOG:
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                print("Notisbook: prazo esgotado; verifique os containers dos runtimes Docker.", file=sys.stderr)
                return
            info = inspect_container(runtime)
            if info is None or not info.running or not info.owned_by(runtime):
                continue
            print(f"Notisbook: parando container {runtime.container}…", file=sys.stderr, flush=True)
            result = docker_cli.run(
                ["stop", "-t", str(FALLBACK_STOP_GRACE_S), runtime.container],
                timeout=max(1.0, deadline - time.monotonic()),
            )
            if result.returncode != 0:
                print(f"Notisbook: não foi possível parar o container {runtime.container}.", file=sys.stderr)
    except (docker_cli.DockerError, OSError) as exc:
        print(f"Notisbook: containers dos runtimes não foram parados ({exc}).", file=sys.stderr)
    finally:
        signal.signal(signal.SIGINT, previous)


def _start_notislake(supervisor: NotislakeSupervisor, sock: socket.socket) -> None:
    """Sobe o MinIO ou sai: falha de subida (exit 1) e sinal/Ctrl+C na subida (128+sinal). A parada fica no `finally` do `main`."""
    print("Notisbook: iniciando o MinIO (notislake)…", file=sys.stderr, flush=True)
    try:
        supervisor.start()
    except StartError as exc:
        sock.close()
        if exc.code == "locked":
            print(
                f"Notisbook: another Notisbook is using the data folder {supervisor.home}. Close it and run notisbook again.",
                file=sys.stderr,
            )
        else:
            print(f"Notisbook: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt as exc:
        sock.close()
        sys.exit(128 + exc.signum if isinstance(exc, TerminationSignal) else 130)


def _stop_notislake(supervisor: NotislakeSupervisor) -> None:
    """Para o MinIO; SIGINT é ignorado (como no fallback dos containers) para um Ctrl+C a mais não abortar a parada."""
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        supervisor.stop()
    finally:
        signal.signal(signal.SIGINT, previous)


class TerminationSignal(KeyboardInterrupt):
    """SIGTERM/SIGHUP recebido antes de o servidor existir; herda de KeyboardInterrupt para seguir o caminho do Ctrl+C."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


class _ShutdownSignals:
    """SIGTERM/SIGHUP pelo caminho ordenado: antes do servidor interrompem a subida; com ele, pedem `should_exit`.

    Depois que o servidor sai (`close()`), os sinais são ignorados para não interromper a parada do MinIO.
    """

    SIGNALS = (signal.SIGTERM, signal.SIGHUP)

    def __init__(self) -> None:
        self.server: uvicorn.Server | None = None
        self._closed = False

    def install(self) -> None:
        for sig in self.SIGNALS:
            signal.signal(sig, self._handle)

    def request_exit(self) -> None:
        if self.server is not None:
            self.server.should_exit = True

    def close(self) -> None:
        self._closed = True

    def _handle(self, signum: int, _frame: object) -> None:
        if self._closed:
            return
        if self.server is None:
            raise TerminationSignal(signum)
        self.server.should_exit = True


def _bind_listener(port: int) -> socket.socket:
    """Abre o socket de escuta antes do uvicorn: porta ocupada falha aqui, sem lifespan, varredura ou parada de containers."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
    except OSError as exc:
        sock.close()
        print(
            f"Notisbook: cannot open http://{HOST}:{port} ({exc.strerror or exc}). The port is in use, possibly by "
            "another Notisbook (for example an older version): close it and run notisbook again, or use --port <other>.",
            file=sys.stderr,
        )
        sys.exit(1)
    sock.set_inheritable(True)
    return sock


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.command == "update":
        sys.exit(update.run(args.target_version))
    if args.command == "uninstall":
        sys.exit(uninstall.run(assume_yes=args.yes))
    if args.check_notislake:
        sys.exit(_check_notislake())
    if args.stop_running:
        sys.exit(_stop_running())
    if args.install_default_runtimes:
        sys.exit(runtimes_bootstrap.run())
    if args.runtimes_summary:
        sys.exit(runtimes_summary.run())
    if args.seed_samples:
        sys.exit(samples_seed.run(if_missing=args.if_missing))
    signals = _ShutdownSignals()
    signals.install()
    try:
        _serve(args, signals)
    except TerminationSignal as exc:
        sys.exit(128 + exc.signum)


def _serve(args: argparse.Namespace, signals: _ShutdownSignals) -> None:
    settings = Settings(port=args.port)
    try:
        ensure_home(settings)
    except OSError as exc:
        failed = exc.filename or settings.home
        print(f"Notisbook: cannot prepare data folder {failed}: {exc.strerror or exc}", file=sys.stderr)
        sys.exit(1)
    # Antes de qualquer kernel: o catálogo precisa existir (e estar migrado) quando o primeiro Spark subir.
    try:
        ensure_catalog_db(settings.home)
    except sqlite3.Error as exc:
        print(f"Notisbook: cannot prepare catalog database in {settings.home}: {exc}", file=sys.stderr)
        sys.exit(1)
    run_onboarding(settings.home, args.root)
    root, source, locked = _resolve_root(args.root, settings.home)
    settings = dataclasses.replace(settings, root=root, root_source=source, root_locked=locked)
    # Antes do bind e do supervisor: uma versão diferente ainda viva precisa soltar a porta e o MinIO.
    try:
        lifecycle.stop_previous_instance(settings.home, __version__)
    except lifecycle.PreviousInstanceError as exc:
        print(f"Notisbook: {exc}", file=sys.stderr)
        sys.exit(1)
    sock = _bind_listener(settings.port)
    supervisor = NotislakeSupervisor(settings.home)
    control = lifecycle.LifecycleControl()
    server: uvicorn.Server | None = None
    try:
        _start_notislake(supervisor, sock)
        try:
            lifecycle.write_record(
                settings.home,
                lifecycle.BackendRecord(pid=os.getpid(), port=settings.port, version=__version__, token=control.token),
            )
        except OSError as exc:
            print(f"Notisbook: cannot write {lifecycle.RUN_DIR}/{lifecycle.BACKEND_FILE} ({exc.strerror or exc}).", file=sys.stderr)
            sys.exit(1)
        url = f"http://{HOST}:{settings.port}/?token={settings.token}"
        print(f"Notisbook: {url}", flush=True)
        if not args.no_browser:
            threading.Timer(1.0, webbrowser.open, args=(url,)).start()
        # Access log desligado: o token da sessão viaja em `?token=` e iria inteiro para o stdout.
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings, supervisor, control),
                log_level="info",
                access_log=False,
                timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S,
            )
        )
        signals.server = server
        control.bind(signals.request_exit)
        try:
            server.run(sockets=[sock])
        except KeyboardInterrupt:
            # Como o `uvicorn.run`: o uvicorn re-emite o SIGINT capturado ao sair, e isso não é erro.
            pass
        finally:
            sock.close()
            # Só para containers se o servidor chegou a servir; senão o lifespan não rodou e o runtime não é nosso.
            if server.started:
                _stop_owned_containers()
    finally:
        # Depois dos containers e fora do lifespan: o duplo SIGINT do `uv run` pula o lifespan, o `finally` não.
        # Daqui em diante SIGTERM/SIGHUP não interrompem a parada do MinIO.
        signals.close()
        sock.close()
        _stop_notislake(supervisor)
        lifecycle.remove_record(settings.home, os.getpid())
    if server is None or not server.started:
        sys.exit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
