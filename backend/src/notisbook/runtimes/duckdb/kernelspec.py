"""Kernelspec do runtime DuckDB e descoberta do env instalado.

Um único kernelspec `duckdb`, fora do glob `spark*` do Spark. O registro fica em
`metadata.notisbook_duckdb`; `kernel.json` nunca recebe credenciais (argv, env ou metadata).
"""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...spark.kernelspec import ENVS_DIR, TRASH_PREFIX, kernels_dir

KERNEL_NAME = "duckdb"
METADATA_KEY = "notisbook_duckdb"
ENV_PREFIX = "duckdb-"
EXTENSIONS_SUBDIR = Path("notisbook") / "duckdb_extensions"


@dataclass(frozen=True)
class InstalledRuntime:
    version: str
    kernel_name: str
    display_name: str
    env_dir: Path
    extension_directory: Path
    extensions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "kernel_name": self.kernel_name,
            "display_name": self.display_name,
            "env_dir": str(self.env_dir),
            "extension_directory": str(self.extension_directory),
            "extensions": list(self.extensions),
        }


def display_name(version: str) -> str:
    return f"DuckDB {version}"


def extension_dir(env_dir: Path) -> Path:
    return env_dir / EXTENSIONS_SUBDIR


def write_kernelspec(version: str, env_dir: Path, extensions: tuple[str, ...]) -> Path:
    """Create or atomically replace `kernel.json`; the previous file survives any failure."""
    python = str(env_dir / "bin" / "python")
    spec = {
        "argv": [python, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": display_name(version),
        "language": "python",
        "metadata": {
            METADATA_KEY: {
                "version": version,
                "extension_directory": str(extension_dir(env_dir)),
                "extensions": list(extensions),
            }
        },
    }
    target = kernels_dir() / KERNEL_NAME
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


def remove_kernelspec() -> None:
    """Apaga o kernelspec; já ausente é ok, qualquer outra falha de E/S sobe como OSError."""
    try:
        shutil.rmtree(kernels_dir() / KERNEL_NAME)
    except FileNotFoundError:
        pass


def is_managed_env(base_dir: Path, env_dir: Path) -> bool:
    return env_dir.parent == base_dir / ENVS_DIR and env_dir.name.startswith(ENV_PREFIX)


def is_removable_env(base_dir: Path, env_dir: Path) -> bool:
    """Só filhos diretos de `envs/` chamados `duckdb-*` ou `.trash-duckdb-*`."""
    return env_dir.parent == base_dir / ENVS_DIR and env_dir.name.startswith((ENV_PREFIX, f"{TRASH_PREFIX}{ENV_PREFIX}"))


def discover(base_dir: Path) -> InstalledRuntime | None:
    """O runtime registrado cujo interpretador vive em `base_dir/envs/duckdb-*`, ou None."""
    spec_dir = kernels_dir() / KERNEL_NAME
    try:
        spec = json.loads((spec_dir / "kernel.json").read_text(encoding="utf-8"))
        python = Path(os.path.abspath(spec["argv"][0]))
        ours = spec["metadata"][METADATA_KEY]
        version = ours["version"]
        extensions = tuple(str(e) for e in ours["extensions"])
        display = str(spec.get("display_name") or display_name(version))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    if not isinstance(version, str) or python.parent.name != "bin":
        return None
    env_dir = python.parent.parent
    if not is_managed_env(base_dir, env_dir):
        return None
    return InstalledRuntime(version, KERNEL_NAME, display, env_dir, extension_dir(env_dir), extensions)
