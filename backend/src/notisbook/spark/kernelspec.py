"""Kernelspec files for Spark environments and discovery of installed ones.

`kernel.json` is written directly (not via `ipykernel install`) so the kernel
gets an explicit `env`: JAVA_HOME plus PYSPARK_PYTHON/PYSPARK_DRIVER_PYTHON,
and never SPARK_HOME/PYTHONPATH. Kernelspecs live in `<home>/kernels`, the only folder the app's
`KernelSpecManager` scans; the global Jupyter folder is read only to migrate or remove legacy specs.
"""

import errno
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jupyter_core.paths import jupyter_data_dir

from .bundles import S3A_BY_HADOOP, S3aSet, bundle_for, installed_hadoop

METADATA_KEY = "notisbook"
ENVS_DIR = "envs"
KERNELS_DIR = "kernels"
TRASH_PREFIX = ".trash-"
LEGACY_PREFIX = ".venv-spark"
# `metadata.notisbook.s3a.store`: the S3A jars live in the shared cache (`<home>/jars`), not inside the env.
STORE_SHARED = "shared"
_DISPLAY_VERSION = re.compile(r"Apache Spark (\d+\.\d+\.\d+)", re.ASCII)
_SPARK_NAME = re.compile(r"spark\d+", re.ASCII)


@dataclass(frozen=True)
class InstalledVersion:
    version: str
    kernel_name: str
    display_name: str
    legacy: bool
    env_dir: Path
    formats: tuple[str, ...] | None = None
    bundle_status: str = "unsupported"
    # S3A jars status (same values as `bundle_status`); `bundle_status` covers only the Delta/Iceberg/Hudi formats.
    s3a_status: str = "unsupported"

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "kernel_name": self.kernel_name,
            "display_name": self.display_name,
            "legacy": self.legacy,
            "env_dir": str(self.env_dir),
            "formats": list(self.formats) if self.formats is not None else None,
            "bundle_status": self.bundle_status,
            "s3a_status": self.s3a_status,
        }


def kernel_name(version: str) -> str:
    return f"spark{version.replace('.', '')}"


def display_name(version: str) -> str:
    return f"Apache Spark {version}"


def is_spark_kernel_name(name: str) -> bool:
    return _SPARK_NAME.fullmatch(name) is not None


def kernels_dir(home: Path) -> Path:
    """Folder with the kernelspecs of this data home (exclusive to the app)."""
    return home / KERNELS_DIR


def legacy_kernels_dir() -> Path:
    """Global Jupyter kernels folder used before specs moved into the home; only migration and uninstall touch it."""
    return Path(jupyter_data_dir()) / "kernels"


class PythonState(Enum):
    USABLE = "usable"
    UNUSABLE = "unusable"  # ausente, symlink quebrado/em laço, não é arquivo ou sem X_OK
    INACCESSIBLE = "inaccessible"  # o teste falhou por permissão/E/S: pode ser um env bom, só bloqueado


def python_state(python: Path) -> PythonState:
    """Classifica o interpretador de um kernelspec (symlinks seguidos); total em E/S, nunca levanta."""
    try:
        mode = python.stat().st_mode
    except (FileNotFoundError, NotADirectoryError, ValueError):
        return PythonState.UNUSABLE
    except OSError as exc:
        return PythonState.UNUSABLE if exc.errno == errno.ELOOP else PythonState.INACCESSIBLE
    usable = stat.S_ISREG(mode) and os.access(python, os.X_OK)
    return PythonState.USABLE if usable else PythonState.UNUSABLE


def python_usable(python: Path) -> bool:
    return python_state(python) is PythonState.USABLE


def conf_dir(env_dir: Path) -> Path:
    return env_dir / "spark-conf"


def jars_dir(env_dir: Path) -> Path:
    return env_dir / "notisbook" / "jars"


def write_kernelspec(home: Path, version: str, env_dir: Path, java_home: str, s3a: S3aSet) -> Path:
    """Create or atomically replace `kernel.json`; the previous file survives any failure."""
    python = str(env_dir / "bin" / "python")
    env = {
        "JAVA_HOME": java_home,
        "PYSPARK_PYTHON": python,
        "PYSPARK_DRIVER_PYTHON": python,
        "SPARK_CONF_DIR": str(conf_dir(env_dir)),
        # The Web UI ignores `spark.driver.bindAddress` and binds to this variable (see `render_base_defaults`).
        "SPARK_LOCAL_IP": "127.0.0.1",
    }
    notisbook: dict[str, Any] = {
        "version": version,
        "s3a": {"hadoop": s3a.hadoop, "revision": s3a.revision, "store": STORE_SHARED},
    }
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
    target = kernels_dir(home) / kernel_name(version)
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


def remove_kernelspec(home: Path, name: str) -> None:
    """Apaga o kernelspec; já ausente é ok, qualquer outra falha de E/S sobe como OSError."""
    try:
        shutil.rmtree(kernels_dir(home) / name)
    except FileNotFoundError:
        pass


def copy_kernel_json(source_dir: Path, target_dir: Path) -> None:
    """Copy `kernel.json` into `target_dir` atomically; an existing one survives any failure."""
    data = (source_dir / "kernel.json").read_bytes()
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target_dir, prefix=".kernel.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target_dir / "kernel.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


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


def s3a_plan(env_dir: Path, version: str, ours: dict[str, Any]) -> tuple[str, S3aSet | None, bool]:
    """S3A status of a managed env, the set its jars follow and whether they live in the shared cache.

    A recorded `s3a` entry must match the current set revision, the Hadoop inside the env and the shared store. Envs installed
    before `s3a` existed that carry a formats bundle keep their jars under `env/notisbook/jars` (old layout).
    Anything else is `outdated` and has to be reinstalled. The set is None unless the status is `installed`.
    """
    hadoop = installed_hadoop(env_dir)
    current = S3A_BY_HADOOP.get(hadoop) if hadoop is not None else None
    recorded = ours.get("s3a")
    if isinstance(recorded, dict):
        if (
            current is not None
            and recorded.get("hadoop") == current.hadoop
            and recorded.get("revision") == current.revision
            and recorded.get("store") == STORE_SHARED
        ):
            return "installed", current, True
        return "outdated", None, True
    if current is not None and isinstance(ours.get("bundle"), dict) and bundle_for(version) is not None:
        # The old layout is only usable while the jars of the current set are still inside the env.
        # is_file() only swallows ENOENT/ENOTDIR/EBADF/ELOOP; EACCES propagates and must not break the listing.
        try:
            complete = all((jars_dir(env_dir) / artifact.filename).is_file() for artifact in current.artifacts)
        except OSError:
            complete = False
        if complete:
            return "installed", current, False
    return "outdated", None, False


def is_managed_env(base_dir: Path, env_dir: Path) -> bool:
    """True para `base_dir/envs/spark-*`: o ambiente gerenciado (não o legado `.venv-spark*`)."""
    return env_dir.parent == base_dir / ENVS_DIR and env_dir.name.startswith("spark-")


def _read_owned(base_dir: Path, spec_dir: Path) -> tuple[InstalledVersion, Path] | None:
    """Spec that points into `base_dir` (managed or legacy env) and the interpreter it names; no existence check."""
    try:
        spec = json.loads((spec_dir / "kernel.json").read_text(encoding="utf-8"))
        raw_python = spec["argv"][0]
        if not isinstance(raw_python, str) or "\x00" in raw_python:
            return None
        python = _abs(raw_python)
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
    is_legacy = legacy and not managed
    s3a_status = "unsupported" if is_legacy else s3a_plan(env_dir, version, ours)[0]
    entry = InstalledVersion(
        version, spec_dir.name, display or display_name(version), is_legacy, env_dir, formats, status, s3a_status
    )
    return entry, python


def owned_specs(base_dir: Path, root: Path) -> list[tuple[Path, InstalledVersion, PythonState]]:
    """`(spec_dir, entry, state)` of the `spark*` specs in `root` that point into `base_dir`.

    Orphans and blocked envs are included with their non-usable `state`; reconciliation and uninstall rely on that.
    """
    try:
        spec_dirs = sorted(p for p in root.glob("spark*") if p.is_dir())
    except OSError:
        return []
    found = []
    for spec_dir in spec_dirs:
        read = _read_owned(base_dir, spec_dir)
        if read is not None:
            found.append((spec_dir, read[0], python_state(read[1])))
    return found


def discover(base_dir: Path) -> list[InstalledVersion]:
    """Installed Spark kernels of this home: the spec points into `base_dir` and its interpreter exists."""
    return [entry for _spec_dir, entry, state in owned_specs(base_dir, kernels_dir(base_dir)) if state is PythonState.USABLE]


def is_removable_env(base_dir: Path, env_dir: Path) -> bool:
    """Only direct children of `envs/` (`spark-*`, `.trash-spark-*`) or legacy `.venv-spark*` may be deleted."""
    if env_dir.parent == base_dir / ENVS_DIR:
        return env_dir.name.startswith(("spark-", f"{TRASH_PREFIX}spark-"))
    return env_dir.parent == base_dir and env_dir.name.startswith(LEGACY_PREFIX)
