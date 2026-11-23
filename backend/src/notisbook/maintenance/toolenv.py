"""Detecção do ambiente de instalação: onde está o `uv` e se este processo roda num `uv tool`.

Fora de um `uv tool` (checkout de desenvolvimento, `uv run`) o app reporta versão `0+unknown` ou
a do checkout; por isso a decisão vem do caminho do interpretador, não da versão.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import __version__

TOOL_NAME = "notisbook"
UV_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class ToolEnv:
    uv: str | None
    managed: bool
    # `uv` sumiu do PATH, mas este processo vive num ambiente de `uv tool` (há `uv-receipt.toml`).
    orphaned: bool
    version: str


def find_uv() -> str | None:
    return shutil.which("uv")


def uv_tool_dir(uv: str) -> Path | None:
    """Pasta de ferramentas do uv (respeita `UV_TOOL_DIR`), ou None se o uv não responder."""
    try:
        result = subprocess.run(
            [uv, "tool", "dir"], capture_output=True, text=True, timeout=UV_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = result.stdout.strip()
    return Path(out) if result.returncode == 0 and out else None


def _in_tool_env(uv: str) -> bool:
    tool_dir = uv_tool_dir(uv)
    if tool_dir is None:
        return False
    # Só o ambiente desta ferramenta: `uv tool uninstall notisbook` não alcança outras.
    return Path(sys.prefix).resolve().is_relative_to((tool_dir / TOOL_NAME).resolve())


def detect() -> ToolEnv:
    uv = find_uv()
    orphaned = uv is None and (Path(sys.prefix) / "uv-receipt.toml").is_file()
    return ToolEnv(uv=uv, managed=uv is not None and _in_tool_env(uv), orphaned=orphaned, version=__version__)
