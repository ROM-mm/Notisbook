"""CLI entry point: `notisbook [--port N] [--root DIR] [--no-browser]`."""

import argparse
import dataclasses
import signal
import socket
import sqlite3
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from uvicorn.config import STARTUP_FAILURE

from . import __version__
from .app import create_app
from .catalog.store import ensure_catalog_db
from .config import DEFAULT_PORT, HOST, Settings, default_root, ensure_home
from .onboarding import run_onboarding
from .preferences import RootRejected, read_notebooks_root, validate_notebooks_root
from .runtimes.docker import catalog as docker_catalog
from .runtimes.docker import cli as docker_cli
from .runtimes.docker.service import inspect_container

# Prazo para a aba/WebSockets abertos soltarem o servidor: sem ele o 1º Ctrl+C espera sem limite e o 2º
# (saída forçada) pula o lifespan, onde os containers são parados.
GRACEFUL_SHUTDOWN_S = 5
# Prazo total do fallback que para os containers do app depois que o servidor sai.
FALLBACK_STOP_BUDGET_S = 20.0
FALLBACK_STOP_GRACE_S = 10


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="notisbook")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def _resolve_root(cli_root: Path | None, home: Path) -> tuple[Path, str, bool]:
    """Raiz inicial e sua origem: `--root` (trava a UI) > preferência salva > `default_root(home)`.

    A preferência salva nunca é criada aqui: se for inválida (mesma validação da API), cai no default com aviso.
    """
    if cli_root is not None:
        return cli_root.expanduser().resolve(), "cli", True
    saved = read_notebooks_root(home)
    if saved is not None:
        try:
            return validate_notebooks_root(saved, home), "saved", False
        except RootRejected as exc:
            print(f"Notisbook: saved notebooks folder {saved} is not usable ({exc.message}); using the default.", file=sys.stderr)
    return default_root(home).resolve(), "default", False


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


def _bind_listener(port: int) -> socket.socket:
    """Abre o socket de escuta antes do uvicorn: porta ocupada falha aqui, sem lifespan, varredura ou parada de containers."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
    except OSError as exc:
        sock.close()
        print(
            f"Notisbook: não foi possível abrir http://{HOST}:{port} ({exc.strerror or exc}); "
            "a porta está em uso, talvez por outro Notisbook. Use --port <outra>.",
            file=sys.stderr,
        )
        sys.exit(1)
    sock.set_inheritable(True)
    return sock


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
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
    sock = _bind_listener(settings.port)
    url = f"http://{HOST}:{settings.port}/?token={settings.token}"
    print(f"Notisbook: {url}", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    # Access log desligado: o token da sessão viaja em `?token=` e iria inteiro para o stdout.
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            log_level="info",
            access_log=False,
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S,
        )
    )
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
    if not server.started:
        sys.exit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
