"""Compila `minio` e `mc` (tags fixas) para macOS e empacota os tarballs do notislake.

Uso: python3 scripts/build_minio.py --out <diretório>
Pré-requisito: apenas `docker`; a compilação ocorre num container `golang` de versão fixa.
Gera `notislake-minio-<tag do minio>-darwin-<arch>.tar.gz` por arquitetura e grava o
manifesto de sha256 em `backend/src/notisbook/notislake/minio_manifest.json`.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "backend" / "src" / "notisbook" / "notislake" / "minio_manifest.json"

GO_IMAGE = "golang:1.24.13"
MINIO_REPO = "https://github.com/minio/minio.git"
MC_REPO = "https://github.com/minio/mc.git"
MINIO_TAG = "RELEASE.2025-10-15T17-29-55Z"
MC_TAG = "RELEASE.2025-08-13T08-35-41Z"
ARCHES = ("arm64",)

# Roda dentro do container. O resultado sai como tar em stdout (sem bind mount, que
# depende dos diretórios compartilhados da VM do Docker); logs vão para stderr.
CONTAINER_SCRIPT = r"""
set -eu
exec 3>&1 1>&2
git clone -q --depth 1 --branch "$MINIO_TAG" "$MINIO_REPO" /tmp/minio-src
git clone -q --depth 1 --branch "$MC_TAG" "$MC_REPO" /tmp/mc-src
out=/tmp/out
mkdir -p "$out"

cd /tmp/minio-src
minio_commit=$(git rev-parse HEAD)
# gen-ldflags.go lê o git local; o prefixo RELEASE reproduz a tag oficial.
minio_ldflags=$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go "${MINIO_TAG#RELEASE.}")
cp LICENSE "$out/LICENSE"

cd /tmp/mc-src
mc_commit=$(git rev-parse HEAD)
mc_version="${MC_TAG#RELEASE.}"
mc_ldflags="-s -w -X github.com/minio/mc/cmd.Version=${mc_version} -X github.com/minio/mc/cmd.ReleaseTag=${MC_TAG} -X github.com/minio/mc/cmd.CopyrightYear=$(echo "$mc_version" | cut -c1-4)"

for arch in $ARCHES; do
  mkdir -p "$out/$arch"
  (cd /tmp/minio-src && CGO_ENABLED=0 GOOS=darwin GOARCH="$arch" \
    go build -trimpath -ldflags "$minio_ldflags" -o "$out/$arch/minio" .)
  (cd /tmp/mc-src && CGO_ENABLED=0 GOOS=darwin GOARCH="$arch" \
    go build -trimpath -ldflags "$mc_ldflags" -o "$out/$arch/mc" .)
done

printf 'minio=%s\nmc=%s\n' "$minio_commit" "$mc_commit" > "$out/commits.txt"
tar -C "$out" -cf - . >&3
"""


class BuildError(RuntimeError):
    """Falha numa etapa do build do pacote notislake."""


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compile_in_container(work: Path) -> Path:
    """Compila no container e extrai o resultado em `work/build`."""
    if shutil.which("docker") is None:
        raise BuildError("comando não encontrado: docker")
    archive = work / "build.tar"
    cmd = [
        "docker", "run", "--rm",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/tmp", "-e", "GOCACHE=/tmp/gocache", "-e", "GOPATH=/tmp/gopath",
        "-e", f"MINIO_TAG={MINIO_TAG}", "-e", f"MC_TAG={MC_TAG}",
        "-e", f"MINIO_REPO={MINIO_REPO}", "-e", f"MC_REPO={MC_REPO}",
        "-e", f"ARCHES={' '.join(ARCHES)}",
        GO_IMAGE, "sh", "-c", CONTAINER_SCRIPT,
    ]
    print(f"$ docker run --rm {GO_IMAGE} (build {MINIO_TAG} / {MC_TAG})", flush=True)
    with archive.open("wb") as stdout:
        result = subprocess.run(cmd, stdout=stdout, check=False)
    if result.returncode != 0:
        raise BuildError(f"docker falhou com exit {result.returncode}")
    build = work / "build"
    build.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(build, filter="data")
    return build


def read_commits(build: Path) -> dict[str, str]:
    commits = dict(
        line.split("=", 1) for line in (build / "commits.txt").read_text().splitlines() if line
    )
    if set(commits) != {"minio", "mc"}:
        raise BuildError("commits.txt inesperado no resultado do container")
    return commits


def source_text(commits: dict[str, str]) -> str:
    return (
        "Fonte dos binários deste pacote (licença AGPLv3, ver LICENSE).\n"
        f"minio: {MINIO_REPO}\n  tag: {MINIO_TAG}\n  commit: {commits['minio']}\n"
        f"mc: {MC_REPO}\n  tag: {MC_TAG}\n  commit: {commits['mc']}\n"
        f"Compilado com {GO_IMAGE}, CGO_ENABLED=0 GOOS=darwin, -trimpath.\n"
    )


def make_tarball(dest: Path, members: list[tuple[str, bytes, int]]) -> None:
    """Escreve o tar.gz de forma determinística (mtime/uid/gid fixos, ordem fixa)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, data, mode in members:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, 0
            tar.addfile(info, io.BytesIO(data))
    with dest.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())


def package(build: Path, out: Path, commits: dict[str, str]) -> dict[str, dict]:
    license_bytes = (build / "LICENSE").read_bytes()
    source_bytes = source_text(commits).encode()
    version = MINIO_TAG.removeprefix("RELEASE.")
    archs: dict[str, dict] = {}
    for arch in ARCHES:
        minio_bin = (build / arch / "minio").read_bytes()
        mc_bin = (build / arch / "mc").read_bytes()
        name = f"notislake-minio-{MINIO_TAG}-darwin-{arch}.tar.gz"
        make_tarball(
            out / name,
            [
                ("minio", minio_bin, 0o755),
                ("mc", mc_bin, 0o755),
                ("LICENSE", license_bytes, 0o644),
                ("SOURCE.txt", source_bytes, 0o644),
            ],
        )
        archs[f"darwin-{arch}"] = {
            "tarball": name,
            "sha256": sha256_of((out / name).read_bytes()),
            "minio": {"sha256": sha256_of(minio_bin)},
            "mc": {"sha256": sha256_of(mc_bin)},
        }
        print(f"gerado {out / name}", flush=True)
    return {
        "schema": 1,
        "tag": MINIO_TAG,
        "version": version,
        "mc_tag": MC_TAG,
        "mc_version": MC_TAG.removeprefix("RELEASE."),
        "commits": commits,
        "archs": archs,
    }


def write_manifest(manifest: dict) -> None:
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, MANIFEST)
    print(f"manifesto gravado em {MANIFEST}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="diretório dos tarballs")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="notislake-build-") as tmp:
            build = compile_in_container(Path(tmp))
            manifest = package(build, out, read_commits(build))
        write_manifest(manifest)
    except BuildError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
