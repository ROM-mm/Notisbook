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


def default_root(home: Path) -> Path:
    """Pasta padrão dos notebooks: `<home>/notebooks`, dentro da pasta de dados do Notisbook."""
    return home / "notebooks"


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
    """Built frontend: `$NOTISBOOK_FRONTEND_DIST`, else `<repo>/frontend/dist` if present, else the copy bundled in the package."""
    configured = os.environ.get("NOTISBOOK_FRONTEND_DIST")
    if configured:
        return Path(configured).expanduser()
    repo_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if repo_dist.is_dir():
        return repo_dist
    return Path(__file__).resolve().parent / "_frontend"


def default_pypi_url() -> str:
    """Base URL of the PyPI JSON API; overridable for mirrors and offline checks."""
    return os.environ.get("NOTISBOOK_PYPI_URL") or "https://pypi.org"


# Marca "root não informada"; comparada por identidade em `__post_init__`, que a substitui pela raiz padrão.
_ROOT_UNSET = Path("/.notisbook-root-unset")


@dataclass(frozen=True)
class Settings:
    port: int = DEFAULT_PORT
    root: Path = _ROOT_UNSET
    home: Path = field(default_factory=default_home)
    pypi_url: str = field(default_factory=default_pypi_url)
    frontend_dist: Path = field(default_factory=default_frontend_dist)
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    # `root` é só a raiz inicial; a viva é `app.state.store.root`. Origem: "cli" | "saved" | "default".
    root_source: str = "default"
    root_locked: bool = False
    host: str = field(default=HOST, init=False)

    def __post_init__(self) -> None:
        if self.root is _ROOT_UNSET:
            object.__setattr__(self, "root", default_root(self.home))

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset({f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"})

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})
