"""Detecção do host suportado: somente Mac Apple silicon (nativo ou sob Rosetta)."""

from __future__ import annotations

import platform
import subprocess

_SYSCTL = "/usr/sbin/sysctl"


def _is_rosetta() -> bool:
    """True quando o processo x86_64 roda traduzido pelo Rosetta num Mac Apple silicon."""
    try:
        out = subprocess.run([_SYSCTL, "-n", "sysctl.proc_translated"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.stdout.strip() == "1"


def is_apple_silicon() -> bool:
    """True em Darwin arm64/aarch64 ou x86_64 traduzido pelo Rosetta."""
    if platform.system() != "Darwin":
        return False
    machine = platform.machine().lower()
    return machine in ("arm64", "aarch64") or (machine == "x86_64" and _is_rosetta())
