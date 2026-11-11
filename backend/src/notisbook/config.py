"""Runtime settings, fixed at process start."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from .spark.bundles import WAREHOUSE_DIR
from .spark.kernelspec import ENVS_DIR

# Bind is always loopback; there is intentionally no way to configure it.
HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def default_root() -> Path:
    return Path.home() / "notebooks"


def default_home() -> Path:
    """Notisbook data root: `$NOTISBOOK_HOME` or `~/.notisbook`; holds `envs/`, `warehouse/` and `catalog.db`."""
    configured = os.environ.get("NOTISBOOK_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".notisbook"


def ensure_home(settings:"Settings") -> None:
    """Create the data root and its subfolders; idempotent. Raises OSError on failure."""
    for folder in (
        settings.home,
        settings.home / ENVS_DIR,
        settings.home / WAREHOUSE_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def default_frontend_dist() -> Path:
    """`$NOTISBOOK_FRONTEND_DIST` or `<repo>/frontend/dist` (this file lives in backend/src/notisbook)."""
    configured = os.environ.get("NOTISBOOK_FRONTEND_DIST")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def default_pypi_url() -> str:
    """Base URL of the PyPI JSON API; overridable for mirrors and offline checks."""
    return os.environ.get("NOTISBOOK_PYPI_URL") or "https://pypi.org"


@dataclass(frozen=True)
class Settings:
    port: int = DEFAULT_PORT
    root: Path = field(default_factory=default_root)
    home: Path = field(default_factory=default_home)
    pypi_url: str = field(default_factory=default_pypi_url)
    frontend_dist: Path = field(default_factory=default_frontend_dist)
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    # `root` é só a raiz inicial; a viva é `app.state.store.root`. Origem: "cli" | "saved" | "default".
    root_source: str = "default"
    root_locked: bool = False
    host: str = field(default=HOST, init=False)

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset({f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"})

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})
