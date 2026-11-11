"""Gera sdist e wheel do Notisbook com o frontend embutido.

Uso: uv run --project backend python scripts/build_release.py
Etapas: build do frontend, cópia para `_frontend/`, `uv build`, conferência
do `index.html` nos dois artefatos e sha256 do sdist.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
DIST = BACKEND / "dist"
EMBEDDED = BACKEND / "src" / "notisbook" / "_frontend"
INDEX_IN_ARCHIVE = "notisbook/_frontend/index.html"


class ReleaseError(RuntimeError):
    """Falha numa etapa do build de release."""


def run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})", flush=True)
    try:
        subprocess.run(cmd, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise ReleaseError(f"comando não encontrado: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise ReleaseError(f"{cmd[0]} falhou com exit {exc.returncode}") from exc


def read_version() -> str:
    with (BACKEND / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def build_frontend() -> None:
    for tool in ("node", "npm"):
        if shutil.which(tool) is None:
            raise ReleaseError(f"{tool} não encontrado no PATH; instale Node.js para compilar o frontend")
    if not (FRONTEND / "node_modules").is_dir():
        run(["npm", "ci"], FRONTEND)
    run(["npm", "run", "build"], FRONTEND)
    if not (FRONTEND / "dist" / "index.html").is_file():
        raise ReleaseError("frontend/dist/index.html ausente após o build")


def embed_frontend() -> None:
    shutil.rmtree(EMBEDDED, ignore_errors=True)
    shutil.copytree(FRONTEND / "dist", EMBEDDED)


def build_packages(version: str) -> tuple[Path, Path]:
    DIST.mkdir(parents=True, exist_ok=True)
    for old in DIST.glob(f"notisbook-{version}*"):
        if old.is_dir():
            shutil.rmtree(old)
        else:
            old.unlink()
    run(["uv", "build", "--sdist", "--wheel", "--out-dir", str(DIST), str(BACKEND)], ROOT)
    sdist = DIST / f"notisbook-{version}.tar.gz"
    wheels = list(DIST.glob(f"notisbook-{version}-*.whl"))
    if not sdist.is_file() or len(wheels) != 1:
        raise ReleaseError(f"artefatos esperados não encontrados em {DIST}")
    return sdist, wheels[0]


def check_contains_index(sdist: Path, wheel: Path, version: str) -> None:
    with tarfile.open(sdist) as tar:
        if f"notisbook-{version}/src/{INDEX_IN_ARCHIVE}" not in tar.getnames():
            raise ReleaseError(f"{sdist.name} não contém {INDEX_IN_ARCHIVE}")
    with zipfile.ZipFile(wheel) as zf:
        if INDEX_IN_ARCHIVE not in zf.namelist():
            raise ReleaseError(f"{wheel.name} não contém {INDEX_IN_ARCHIVE}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    try:
        version = read_version()
        build_frontend()
        embed_frontend()
        sdist, wheel = build_packages(version)
        check_contains_index(sdist, wheel, version)
    except ReleaseError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"sdist: {sdist}")
    print(f"wheel: {wheel}")
    print(f"sha256 {sdist.name}: {sha256(sdist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
