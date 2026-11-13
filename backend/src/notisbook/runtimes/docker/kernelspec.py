"""Kernelspec `notisbook-docker-<key>` do runtime Docker e leitura do que está registrado.

O registro é o próprio kernelspec (padrão do Local): `kernel.json` com `metadata.notisbook_docker`
e `packages.json` ao lado. `argv[0]` é o Python do app, regravado pelo app ao criar o kernel;
o kernel em si roda no container via `launch`. `interrupt_mode` é `message` porque `docker exec`
não repassa SIGINT.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from ...spark.kernelspec import kernels_dir
from . import catalog

METADATA_KEY = "notisbook_docker"
PACKAGES_FILE = "packages.json"
LAUNCH_MODULE = "notisbook.runtimes.docker.launch"


def _write_json_atomic(path: Path, data: Any) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
            handle.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def kernelspec_dir(runtime: catalog.DockerRuntime) -> Path:
    return kernels_dir() / runtime.kernel_name


def build_spec(runtime: catalog.DockerRuntime, python: str) -> dict[str, Any]:
    return {
        # `-I` mantém a pasta do notebook (cwd) fora do sys.path do launcher.
        "argv": [
            python,
            "-I",
            "-m",
            LAUNCH_MODULE,
            "--key",
            runtime.key,
            "-f",
            "{connection_file}",
        ],
        "display_name": runtime.label,
        "language": "python",
        "interrupt_mode": "message",
        "metadata": {
            METADATA_KEY: {
                "key": runtime.key,
                "image": runtime.image,
                "container": runtime.container,
                "formats": list(runtime.formats),
            }
        },
    }


def write_kernelspec(
    runtime: catalog.DockerRuntime,
    packages: dict[str, Any] | None = None,
    python: str | None = None,
) -> Path:
    """Cria ou substitui o kernelspec de forma atômica; `kernel.json` sai por último (é ele que registra)."""
    target = kernelspec_dir(runtime)
    target.mkdir(parents=True, exist_ok=True)
    if packages is not None:
        _write_json_atomic(target / PACKAGES_FILE, packages)
    _write_json_atomic(
        target / "kernel.json", build_spec(runtime, python or sys.executable)
    )
    return target / "kernel.json"


def remove_kernelspec(runtime: catalog.DockerRuntime) -> None:
    """Apaga a pasta do kernelspec do runtime; já ausente é ok, outra falha de E/S sobe como OSError."""
    try:
        shutil.rmtree(kernelspec_dir(runtime))
    except FileNotFoundError:
        pass


def read_registration(runtime: catalog.DockerRuntime) -> dict[str, Any] | None:
    """`metadata.notisbook_docker` do kernelspec, ou None se não registrado ou ilegível."""
    try:
        spec = json.loads(
            (kernelspec_dir(runtime) / "kernel.json").read_text(encoding="utf-8")
        )
        meta = spec["metadata"][METADATA_KEY]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return meta if isinstance(meta, dict) and meta.get("key") == runtime.key else None


def read_packages(runtime: catalog.DockerRuntime) -> dict[str, Any] | None:
    try:
        data = json.loads(
            (kernelspec_dir(runtime) / PACKAGES_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
