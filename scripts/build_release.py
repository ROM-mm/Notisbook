"""Gera sdist, wheel, constraints e SHA256SUMS do Notisbook com o frontend embutido.

Uso: uv run --project backend python scripts/build_release.py [--checksums-only]
Etapas: build do frontend, cópia para `_frontend/`, `uv build`, conferência
do `index.html`, constraints do uv.lock, gate de wheel binária (macOS arm64),
SHA256SUMS (inclui o install.sh) e sha256 da wheel e do sdist.
`--checksums-only` só regenera o SHA256SUMS, exigindo os tarballs do MinIO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
DIST = BACKEND / "dist"
EMBEDDED = BACKEND / "src" / "notisbook" / "_frontend"
INDEX_IN_ARCHIVE = "notisbook/_frontend/index.html"
MINIO_DIST = DIST / "notislake"
MINIO_MANIFEST = BACKEND / "src" / "notisbook" / "notislake" / "minio_manifest.json"
SUMS_NAME = "SHA256SUMS"
# Publicado como asset ao lado da wheel; `notisbook update` o confere contra o SHA256SUMS antes de executá-lo.
INSTALL_SCRIPT = ROOT / "install.sh"
GATE_PYTHON = "3.12"
GATE_PLATFORMS = ("aarch64-apple-darwin",)
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)")


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


def build_frontend(*, skip_npm_ci: bool = False) -> None:
    for tool in ("node", "npm"):
        if shutil.which(tool) is None:
            raise ReleaseError(f"{tool} não encontrado no PATH; instale Node.js para compilar o frontend")
    if not skip_npm_ci:
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


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in text.splitlines():
        match = PIN_RE.match(line.strip())
        if match:
            pins[normalize(match.group(1))] = match.group(2)
    return pins


def export_constraints(version: str) -> Path:
    """Exporta as versões exatas do uv.lock (runtime, sem hashes: decisão D5)."""
    constraints = DIST / f"constraints-{version}.txt"
    run(
        [
            "uv", "export", "--project", str(BACKEND), "--frozen", "--no-dev",
            "--no-emit-project", "--no-hashes", "--format", "requirements-txt",
            "--output-file", str(constraints),
        ],
        ROOT,
    )
    if not parse_pins(constraints.read_text()):
        raise ReleaseError(f"{constraints.name} sem nenhum pin")
    return constraints


def check_binary_wheels(constraints: Path) -> None:
    """Falha se alguma dependência não tiver wheel binária nas plataformas-alvo.

    O `install.sh` usa `uv tool install --no-build`; sem wheel a instalação
    do usuário quebraria. Também exige que a resolução reproduza os pins.
    """
    expected = parse_pins(constraints.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        for platform in GATE_PLATFORMS:
            out = Path(tmp) / f"resolved-{platform}.txt"
            try:
                run(
                    [
                        "uv", "pip", "compile", str(constraints), "--no-header", "--no-annotate",
                        "--python-version", GATE_PYTHON, "--python-platform", platform,
                        "--only-binary", ":all:", "--output-file", str(out),
                    ],
                    ROOT,
                )
            except ReleaseError as exc:
                raise ReleaseError(
                    f"gate de wheel binária falhou para {platform} (Python {GATE_PYTHON}): {exc}"
                ) from exc
            resolved = parse_pins(out.read_text())
            diverged = sorted(
                f"{name}: constraints={ver} resolvido={resolved.get(name, 'ausente')}"
                for name, ver in expected.items()
                if resolved.get(name) != ver and name in resolved
            ) + sorted(f"{n}: resolvido fora das constraints ({v})" for n, v in resolved.items() if n not in expected)
            if diverged:
                raise ReleaseError(f"versões divergentes em {platform}: " + "; ".join(diverged))
            print(f"gate de wheel binária ok: {platform} ({len(resolved)} pacotes)", flush=True)


def minio_tarball_names() -> list[str]:
    with MINIO_MANIFEST.open("rb") as fh:
        archs = json.load(fh)["archs"]
    return [archs[key]["tarball"] for key in sorted(archs)]


def stage_minio_tarballs(*, required: bool) -> list[str]:
    """Copia os tarballs de `dist/notislake/` para `dist/`.

    O SHA256SUMS usa nomes base e é conferido num diretório plano com os assets
    baixados da release; por isso os tarballs precisam estar ao lado da wheel.
    """
    names = minio_tarball_names()
    missing = [n for n in names if not (MINIO_DIST / n).is_file()]
    if missing and required:
        raise ReleaseError(f"tarballs do MinIO ausentes em {MINIO_DIST}: {', '.join(missing)}")
    if missing:
        print(
            f"aviso: tarballs do MinIO ausentes em {MINIO_DIST} ({', '.join(missing)}); "
            f"{SUMS_NAME} sai sem eles. Rode build_minio.py e depois "
            "`build_release.py --checksums-only`.",
            file=sys.stderr,
        )
        return []
    for name in names:
        shutil.copy2(MINIO_DIST / name, DIST / name)
    return names


def write_checksums(version: str, *, require_minio: bool) -> Path:
    wheels = list(DIST.glob(f"notisbook-{version}-*.whl"))
    constraints = DIST / f"constraints-{version}.txt"
    if len(wheels) != 1 or not constraints.is_file():
        raise ReleaseError(f"wheel e constraints de {version} não encontradas em {DIST}")
    if not INSTALL_SCRIPT.is_file():
        raise ReleaseError(f"{INSTALL_SCRIPT.name} não encontrado em {ROOT}")
    names = [wheels[0].name, constraints.name, *stage_minio_tarballs(required=require_minio)]
    entries = [(DIST / n, n) for n in names] + [(INSTALL_SCRIPT, INSTALL_SCRIPT.name)]
    sums = DIST / SUMS_NAME
    sums.write_text("".join(f"{sha256(path)}  {name}\n" for path, name in entries))
    return sums


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera sdist e wheel do Notisbook.")
    parser.add_argument(
        "--skip-npm-ci",
        action="store_true",
        help="pula `npm ci` e reaproveita node_modules (só para desenvolvimento; a release usa npm ci)",
    )
    parser.add_argument(
        "--checksums-only",
        action="store_true",
        help="só regenera o SHA256SUMS (wheel, constraints e tarballs do MinIO, que passam a ser obrigatórios)",
    )
    args = parser.parse_args(argv)
    try:
        version = read_version()
        if args.checksums_only:
            print(f"{SUMS_NAME}: {write_checksums(version, require_minio=True)}")
            return 0
        build_frontend(skip_npm_ci=args.skip_npm_ci)
        embed_frontend()
        sdist, wheel = build_packages(version)
        check_contains_index(sdist, wheel, version)
        constraints = export_constraints(version)
        check_binary_wheels(constraints)
        sums = write_checksums(version, require_minio=False)
    except ReleaseError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"sdist: {sdist}")
    print(f"wheel: {wheel}")
    print(f"constraints: {constraints}")
    print(f"{SUMS_NAME}: {sums}")
    print(f"sha256 {wheel.name}: {sha256(wheel)}")
    print(f"sha256 {sdist.name}: {sha256(sdist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
