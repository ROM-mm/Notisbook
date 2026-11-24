"""Kernelspec do runtime DuckDB e descoberta do env instalado.

Um kernelspec por versão, `duckdb-<maj>-<min>-<patch>`, fora do glob `spark*` do Spark. O nome legado `duckdb`
(instalação anterior ao multiversão) continua sendo descoberto. O registro fica em `metadata.notisbook_duckdb`;
`kernel.json` nunca recebe credenciais (argv, env ou metadata).
"""

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...spark.kernelspec import ENVS_DIR, TRASH_PREFIX, kernels_dir
from .manifest import is_valid_version, version_key

# Nome legado e alias: sem kernelspec instalado com este nome, o serviço de kernels resolve para o `duckdb-*` mais novo.
KERNEL_NAME = "duckdb"
KERNEL_PREFIX = "duckdb-"
_VERSIONED_NAME = re.compile(r"duckdb-(\d+)-(\d+)-(\d+)", re.ASCII)
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


def kernel_name(version: str) -> str:
    return f"{KERNEL_PREFIX}{version.replace('.', '-')}"


def is_duckdb_kernel_name(name: str) -> bool:
    """O nome legado `duckdb` ou `duckdb-<maj>-<min>-<patch>`."""
    return name == KERNEL_NAME or _VERSIONED_NAME.fullmatch(name) is not None


def version_of_kernel_name(name: str) -> str | None:
    """`2.0.1` para `duckdb-2-0-1`; None para o nome legado ou qualquer outro."""
    match = _VERSIONED_NAME.fullmatch(name)
    return ".".join(match.groups()) if match else None


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
    """Apaga o kernelspec `name` (legado ou por versão); quem chama escolhe só os gerenciados via `discover`.

    Já ausente é ok, qualquer outra falha de E/S sobe como OSError.
    """
    if not is_duckdb_kernel_name(name):
        raise ValueError(f"not a DuckDB kernel name: {name!r}")
    try:
        shutil.rmtree(kernels_dir() / name)
    except FileNotFoundError:
        pass


def _spec_dirs() -> list[Path]:
    root = kernels_dir()
    try:
        return sorted(p for p in root.iterdir() if is_duckdb_kernel_name(p.name) and p.is_dir())
    except OSError:
        return []


def is_managed_env(base_dir: Path, env_dir: Path) -> bool:
    return env_dir.parent == base_dir / ENVS_DIR and env_dir.name.startswith(ENV_PREFIX)


def is_removable_env(base_dir: Path, env_dir: Path) -> bool:
    """Só filhos diretos de `envs/` chamados `duckdb-*` ou `.trash-duckdb-*`."""
    return env_dir.parent == base_dir / ENVS_DIR and env_dir.name.startswith((ENV_PREFIX, f"{TRASH_PREFIX}{ENV_PREFIX}"))


def _read(spec_dir: Path, base_dir: Path) -> InstalledRuntime | None:
    try:
        spec = json.loads((spec_dir / "kernel.json").read_text(encoding="utf-8"))
        python = Path(os.path.abspath(spec["argv"][0]))
        ours = spec["metadata"][METADATA_KEY]
        version = ours["version"]
        extensions = tuple(str(e) for e in ours["extensions"])
        display = str(spec.get("display_name") or display_name(version))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    if not isinstance(version, str) or not is_valid_version(version) or python.parent.name != "bin":
        return None
    # O nome do diretório precisa bater com a versão registrada (ou ser o legado `duckdb`).
    if spec_dir.name not in (KERNEL_NAME, kernel_name(version)):
        return None
    env_dir = python.parent.parent
    if not is_managed_env(base_dir, env_dir):
        return None
    return InstalledRuntime(version, spec_dir.name, display, env_dir, extension_dir(env_dir), extensions)


def discover(base_dir: Path) -> list[InstalledRuntime]:
    """Runtimes registrados cujo interpretador vive em `base_dir/envs/duckdb-*`, do mais novo ao mais antigo.

    Inclui o kernelspec legado `duckdb`, se existir.
    """
    found = [entry for d in _spec_dirs() if (entry := _read(d, base_dir)) is not None]
    return sorted(found, key=lambda e: (version_key(e.version), e.kernel_name), reverse=True)
