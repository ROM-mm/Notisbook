"""Famílias de fonte instaladas no macOS, via `osascript` (JXA).

O texto do script é constante: nenhuma entrada do usuário chega ao processo. O resultado fica em
cache de memória (cálculo único; só uma execução por vez) e só `refresh=True` o recalcula.
"""

import json
import re
import subprocess
import sys
import threading
from typing import Literal, TypedDict

OSASCRIPT = "/usr/bin/osascript"
TIMEOUT_SECONDS = 5
MAX_FAMILIES = 2000
MAX_NAME = 64

Status = Literal["ok", "unsupported", "unavailable"]

_SCRIPT = (
    "ObjC.import('AppKit');"
    "JSON.stringify(ObjC.deepUnwrap($.NSFontManager.sharedFontManager.availableFontFamilies));"
)

# Mesmo critério de `isValidFontName` no frontend: o nome vira valor CSS entre aspas.
_NAME_PATTERN = re.compile(r"^[^\"'\\;{}\x00-\x1f\x7f]+$")


class SystemFonts(TypedDict):
    status: Status
    families: list[str]


_lock = threading.Lock()
_cache: list[str] | None = None


def _valid_name(name: object) -> bool:
    return (
        isinstance(name, str)
        and name == name.strip()
        and 0 < len(name) <= MAX_NAME
        and not name.startswith(".")
        and _NAME_PATTERN.match(name) is not None
    )


def _filter(names: object) -> list[str]:
    if not isinstance(names, list):
        return []
    unique = {name for name in names if _valid_name(name)}
    return sorted(unique, key=str.casefold)[:MAX_FAMILIES]


def _query() -> list[str] | None:
    """Consulta o sistema; `None` em falha, timeout ou saída inesperada."""
    try:
        proc = subprocess.run(
            [OSASCRIPT, "-l", "JavaScript", "-e", _SCRIPT],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return _filter(json.loads(proc.stdout.strip() or proc.stderr.strip()))
    except ValueError:
        return None


def list_system_fonts(refresh: bool = False) -> SystemFonts:
    """Lista as famílias do sistema; bloqueante (rode em threadpool). Falhas não entram no cache."""
    global _cache
    if sys.platform != "darwin":
        return {"status": "unsupported", "families": []}
    with _lock:
        if refresh or _cache is None:
            _cache = _query()
        families = _cache
    if families is None:
        return {"status": "unavailable", "families": []}
    return {"status": "ok", "families": list(families)}
