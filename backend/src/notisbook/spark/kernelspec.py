"""Kernelspec files for Spark environments and discovery of installed ones.

`kernel.json` is written directly (not via `ipykernel install`) so the kernel
gets an explicit `env`: JAVA_HOME plus PYSPARK_PYTHON/PYSPARK_DRIVER_PYTHON,
and never SPARK_HOME/PYTHONPATH. Kernelspecs go to the user kernels dir, which
honours JUPYTER_DATA_DIR (the only location `jupyter_client` scans here).
"""

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jupyter_core.paths import jupyter_data_dir

from .bundles import bundle_for

METADATA_KEY = "notisbook"
ENVS_DIR = "envs"
TRASH_PREFIX = ".trash-"
LEGACY_PREFIX = ".venv-spark"
_DISPLAY_VERSION = re.compile(r"Apache Spark (\d+\.\d+\.\d+)", re.ASCII)


@dataclass(frozen=True)
class InstalledVersion:
    version: str
    kernel_name: str
    display_name: str
    legacy: bool
    env_dir: Path
    formats: tuple[str, ...] | None = None
    bundle_status: str = "unsupported"

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "kernel_name": self.kernel_name,
            "display_name": self.display_name,
            "legacy": self.legacy,
            "env_dir": str(self.env_dir),
            "formats": list(self.formats) if self.formats is not None else None,
            "bundle_status": self.bundle_status,
        }


def kernel_name(version: str) -> str:
    return f"spark{version.replace('.', '')}"


def display_name(version: str) -> str:
    return f"Apache Spark {version}"


def kernels_dir() -> Path:
    return Path(jupyter_data_dir()) / "kernels"


def conf_dir(env_dir: Path) -> Path:
    return env_dir / "spark-conf"


def jars_dir(env_dir: Path) -> Path:
    return env_dir / "notisbook" / "jars"


def write_kernelspec(version: str, env_dir: Path, java_home: str) -> Path:
    """Create or atomically replace `kernel.json`; the previous file survives any failure."""
    python = str(env_dir / "bin" / "python")
    env = {
        "JAVA_HOME": java_home,
        "PYSPARK_PYTHON": python,
        "PYSPARK_DRIVER_PYTHON": python,
        "SPARK_CONF_DIR": str(conf_dir(env_dir)),
    }
    notisbook: dict[str, Any] = {"version": version}
    bundle = bundle_for(version)
    if bundle is not None:
        notisbook["bundle"] = {"key": bundle.key, "line": bundle.line, "revision": bundle.revision, "formats": list(bundle.formats)}
    spec = {
        "argv": [python, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": display_name(version),
        "language": "python",
        "env": env,
        "metadata": {METADATA_KEY: notisbook},
    }
    target = kernels_dir() / kernel_name(version)
    target.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target, prefix=".kernel.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(spec, handle, indent=1)
            handle.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, target / "kernel.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target / "kernel.json"


def remove_kernelspec(name: str) -> None:
    """Apaga o kernelspec; já ausente é ok, qualquer outra falha de E/S sobe como OSError."""
    try:
        shutil.rmtree(kernels_dir() / name)
    except FileNotFoundError:
        pass


def _abs(path: str | Path) -> Path:
    return Path(os.path.abspath(path))


def _bundle_info(version: str, recorded: Any) -> tuple[tuple[str, ...] | None, str]:
    """Formats recorded in the kernelspec and how that record compares with the current matrix."""
    expected = bundle_for(version)
    if not isinstance(recorded, dict):
        return None, "unsupported" if expected is None else "missing"
    formats = recorded.get("formats")
    listed = tuple(f for f in formats if isinstance(f, str)) if isinstance(formats, list) else None
    if expected is None:
        return listed, "unsupported"
    # Metadata written before `key` existed never matches, so it is reported as outdated.
    if recorded.get("key") != expected.key or recorded.get("revision") != expected.revision:
        return listed, "outdated"
    return listed, "installed"


def is_managed_env(base_dir: Path, env_dir: Path) -> bool:
    """True para `base_dir/envs/spark-*`: o ambiente gerenciado (não o legado `.venv-spark*`)."""
    return env_dir.parent == base_dir / ENVS_DIR and env_dir.name.startswith("spark-")


def _entry(base_dir: Path, spec_dir: Path) -> InstalledVersion | None:
    try:
        spec = json.loads((spec_dir / "kernel.json").read_text(encoding="utf-8"))
        python = _abs(spec["argv"][0])
        display = str(spec.get("display_name", ""))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    if not python.is_relative_to(base_dir) or python.parent.name != "bin":
        return None
    env_dir = python.parent.parent
    managed = is_managed_env(base_dir, env_dir)
    legacy = env_dir.parent == base_dir and env_dir.name.startswith(LEGACY_PREFIX)
    if not (managed or legacy):
        return None
    metadata = spec.get("metadata")
    ours = metadata.get(METADATA_KEY) if isinstance(metadata, dict) else None
    ours = ours if isinstance(ours, dict) else {}
    declared = ours.get("version")
    match = _DISPLAY_VERSION.fullmatch(display)
    version = declared if isinstance(declared, str) else (match.group(1) if match else None)
    if version is None:
        return None
    formats, status = _bundle_info(version, ours.get("bundle"))
    return InstalledVersion(
        version, spec_dir.name, display or display_name(version), legacy and not managed, env_dir, formats, status
    )


def discover(base_dir: Path) -> list[InstalledVersion]:
    """Kernelspecs whose interpreter lives under `base_dir/envs/` or a legacy `.venv-spark*`."""
    root = kernels_dir()
    if not root.is_dir():
        return []
    entries = (_entry(base_dir, spec_dir) for spec_dir in sorted(root.glob("spark*")) if spec_dir.is_dir())
    return [entry for entry in entries if entry is not None]


def is_removable_env(base_dir: Path, env_dir: Path) -> bool:
    """Only direct children of `envs/` (`spark-*`, `.trash-spark-*`) or legacy `.venv-spark*` may be deleted."""
    if env_dir.parent == base_dir / ENVS_DIR:
        return env_dir.name.startswith(("spark-", f"{TRASH_PREFIX}spark-"))
    return env_dir.parent == base_dir and env_dir.name.startswith(LEGACY_PREFIX)
