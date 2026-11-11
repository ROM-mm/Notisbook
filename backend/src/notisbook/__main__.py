"""CLI entry point: `notisbook [--port N] [--root DIR] [--no-browser]`."""

import argparse
import dataclasses
import sqlite3
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .app import create_app
from .catalog.store import ensure_catalog_db
from .config import DEFAULT_PORT, HOST, Settings, default_root, ensure_home
from .preferences import RootRejected, read_notebooks_root, validate_notebooks_root


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="notisbook")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def _resolve_root(cli_root: Path | None, home: Path) -> tuple[Path, str, bool]:
    """Raiz inicial e sua origem: `--root` (trava a UI) > preferência salva > `default_root()`.

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
    return default_root().resolve(), "default", False


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
    root, source, locked = _resolve_root(args.root, settings.home)
    settings = dataclasses.replace(settings, root=root, root_source=source, root_locked=locked)
    url = f"http://{HOST}:{settings.port}/?token={settings.token}"
    print(f"Notisbook: {url}", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    # Access log desligado: o token da sessão viaja em `?token=` e iria inteiro para o stdout.
    uvicorn.run(create_app(settings), host=HOST, port=settings.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
