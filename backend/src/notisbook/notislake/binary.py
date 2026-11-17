"""Localiza o pacote `minio`/`mc` distribuído, valida contra o manifesto e instala em `<home>/minio/bin/`.

O pacote vem de `$NOTISBOOK_MINIO_DIST` (tarball ou diretório); sem ela, do diretório padrão
`${XDG_DATA_HOME:-~/.local/share}/notisbook/notislake`, onde o `install.sh` o coloca. O sha256 esperado fica em
`minio_manifest.json`; nada é instalado se algo divergir. A instalação é atômica por arquivo
(temporário no mesmo diretório + `os.replace`) e idempotente. Não sobe o MinIO.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from ..config import default_home

logger = logging.getLogger(__name__)

DIST_ENV = "NOTISBOOK_MINIO_DIST"
DEFAULT_DIST_DIR = "~/.local/share/notisbook/notislake"
_XDG_DIST_SUFFIX = ("notisbook", "notislake")
MANIFEST_PATH = Path(__file__).with_name("minio_manifest.json")
BINARIES = ("minio", "mc")
_INSTALL_MODE = 0o755
_CHUNK = 1024 * 1024
# Folga sobre os ~110 MB do maior binário; barra tarball que declara tamanho absurdo.
_MAX_MEMBER_BYTES = 1024 * 1024 * 1024
_ARCH_BY_MACHINE = {"arm64": "darwin-arm64", "aarch64": "darwin-arm64", "x86_64": "darwin-amd64", "amd64": "darwin-amd64"}


class BinaryError(Exception):
    """Base dos erros de localização/instalação do binário."""


class BinaryNotInstalledError(BinaryError):
    """Pacote não encontrado: `$NOTISBOOK_MINIO_DIST` inexistente ou diretório padrão ausente."""


class BinaryIntegrityError(BinaryError):
    """sha256 divergente do manifesto, tarball inseguro/corrompido ou conteúdo incompleto."""


class UnsupportedPlatformError(BinaryError):
    """Sistema/arquitetura sem entrada no manifesto."""


@dataclass(frozen=True)
class InstalledMinio:
    tag: str
    minio: Path
    mc: Path


def _tag_for(name: str, tag: str) -> str:
    return f"{name}-{tag}"


def _sha256_stream(src: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := src.read(_CHUNK):
        digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str | None:
    """sha256 do arquivo regular, ou None se ausente/ilegível/não regular."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as handle:
            return _sha256_stream(handle)
    except OSError:
        return None


def _invalid_manifest(detail: str) -> BinaryError:
    return BinaryError(f"manifesto inválido em {MANIFEST_PATH}: {detail}")


def _require_str(container: object, key: str, where: str) -> str:
    value = container.get(key) if isinstance(container, dict) else None
    if not isinstance(value, str) or not value:
        raise _invalid_manifest(f"'{where}{key}' ausente ou não é texto")
    return value


def _load_manifest() -> dict:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BinaryError(f"manifesto ilegível em {MANIFEST_PATH}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise _invalid_manifest("raiz não é um objeto")
    tag = _require_str(manifest, "tag", "")
    # A tag compõe o nome do arquivo instalado; separadores escapariam de <home>/minio/bin.
    if "/" in tag or "\\" in tag or tag in (".", "..") or "\x00" in tag:
        raise _invalid_manifest("'tag' contém caracteres inválidos")
    if not isinstance(manifest.get("archs"), dict):
        raise _invalid_manifest("'archs' ausente ou não é objeto")
    return manifest


def _arch_entry(manifest: dict) -> dict:
    arch = _ARCH_BY_MACHINE.get(platform.machine().lower()) if platform.system() == "Darwin" else None
    entry = manifest["archs"].get(arch) if arch else None
    if not isinstance(entry, dict):
        raise UnsupportedPlatformError(f"sem binário notislake para '{platform.system()}/{platform.machine()}'")
    where = f"archs.{arch}."
    _require_str(entry, "tarball", where)
    _require_str(entry, "sha256", where)
    for name in BINARIES:
        _require_str(entry.get(name), "sha256", f"{where}{name}.")
    return entry


def default_dist_dir() -> Path:
    """Diretório padrão do pacote: `$XDG_DATA_HOME/notisbook/notislake` ou `~/.local/share/notisbook/notislake`."""
    xdg = Path(os.environ.get("XDG_DATA_HOME", "").strip()).expanduser()
    # A spec XDG manda ignorar valor relativo (inclui o vazio, que vira ".").
    if xdg.is_absolute():
        return xdg.joinpath(*_XDG_DIST_SUFFIX)
    return Path(DEFAULT_DIST_DIR).expanduser()


def _resolve_dist() -> Path:
    raw = os.environ.get(DIST_ENV, "").strip()
    if not raw:
        dist = default_dist_dir()
        if not dist.exists():
            raise BinaryNotInstalledError(f"MinIO package not found: looked in {dist}; set {DIST_ENV} to the package directory or tarball")
        return dist
    dist = Path(raw).expanduser()
    if not dist.exists():
        raise BinaryNotInstalledError(f"binário não instalado: {DIST_ENV}={dist} não existe")
    return dist


def _expect(sha: str, expected: str, label: str) -> None:
    if sha != expected:
        raise BinaryIntegrityError(f"sha256 de {label} diverge do manifesto")


def _write_error(bin_dir: Path, exc: OSError) -> BinaryError:
    return BinaryError(f"não foi possível gravar em {bin_dir}: {exc}")


def _guard_write(bin_dir: Path, op, *args) -> None:
    try:
        op(*args)
    except OSError as exc:
        raise _write_error(bin_dir, exc) from exc


def _new_temp(bin_dir: Path, name: str) -> tuple[BinaryIO, Path]:
    try:
        fd, tmp_name = tempfile.mkstemp(dir=bin_dir, prefix=f".{name}-", suffix=".tmp")
    except OSError as exc:
        raise _write_error(bin_dir, exc) from exc
    return os.fdopen(fd, "wb"), Path(tmp_name)


def _stage_stream(src: BinaryIO, bin_dir: Path, name: str, expected: str) -> Path:
    """Copia `src` para um temporário calculando o sha256 do que foi gravado; devolve o temporário verificado.

    Erro de leitura de `src` sai como veio (OSError); erro de escrita no destino vira `BinaryError`.
    """
    out, tmp = _new_temp(bin_dir, name)
    try:
        digest = hashlib.sha256()
        with out:
            while chunk := src.read(_CHUNK):
                digest.update(chunk)
                _guard_write(bin_dir, out.write, chunk)
            _guard_write(bin_dir, out.flush)
            _guard_write(bin_dir, os.fsync, out.fileno())
        _expect(digest.hexdigest(), expected, name)
        _guard_write(bin_dir, os.chmod, tmp, _INSTALL_MODE)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _safe_member_name(name: str) -> str | None:
    """Nome normalizado do membro, ou None se absoluto, com `..`, barra invertida ou NUL."""
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        return None
    parts = [p for p in PurePosixPath(name).parts if p != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _stage_from_tarball(tarball: Path, bin_dir: Path, entry: dict, wanted: list[str]) -> dict[str, Path]:
    """Valida todos os membros e extrai só os `wanted` (arquivos regulares) para temporários verificados."""
    staged: dict[str, Path] = {}
    try:
        with tarfile.open(tarball, "r:gz") as tar:
            for member in tar:
                name = _safe_member_name(member.name)
                if name is None or not (member.isreg() or member.isdir()):
                    raise BinaryIntegrityError(f"tarball recusado: membro inseguro '{member.name}'")
                if name not in wanted or not member.isreg():
                    continue
                if name in staged or member.size > _MAX_MEMBER_BYTES:
                    raise BinaryIntegrityError(f"tarball recusado: membro '{name}' duplicado ou grande demais")
                src = tar.extractfile(member)
                if src is None:
                    raise BinaryIntegrityError(f"tarball recusado: '{name}' ilegível")
                with src:
                    staged[name] = _stage_stream(src, bin_dir, name, entry[name]["sha256"])
        missing = [n for n in wanted if n not in staged]
        if missing:
            raise BinaryIntegrityError(f"tarball sem os binários esperados: {', '.join(missing)}")
    except (tarfile.TarError, EOFError, OSError) as exc:
        _discard(staged)
        raise BinaryIntegrityError(f"tarball ilegível: {exc}") from exc
    except BaseException:
        _discard(staged)
        raise
    return staged


def _stage_from_directory(dist: Path, bin_dir: Path, entry: dict, wanted: list[str]) -> dict[str, Path]:
    staged: dict[str, Path] = {}
    try:
        for name in wanted:
            source = dist / name
            if source.is_symlink() or not source.is_file():
                raise BinaryIntegrityError(f"{name} ausente (ou não é arquivo regular) em {dist}")
            with source.open("rb") as src:
                staged[name] = _stage_stream(src, bin_dir, name, entry[name]["sha256"])
    except OSError as exc:
        # Escritas já viram BinaryError em _guard_write; um OSError aqui é leitura da origem.
        _discard(staged)
        raise BinaryIntegrityError(f"origem ilegível em {dist}: {exc}") from exc
    except BaseException:
        _discard(staged)
        raise
    return staged


def _discard(staged: dict[str, Path]) -> None:
    for tmp in staged.values():
        tmp.unlink(missing_ok=True)


def _find_tarball(dist: Path, entry: dict) -> Path | None:
    """Tarball a usar: o próprio `dist` (arquivo) ou o do manifesto dentro do diretório; None = binários soltos."""
    if dist.is_file():
        return dist
    candidate = dist / entry["tarball"]
    return candidate if candidate.is_file() else None


def _prune_other_tags(bin_dir: Path, keep: set[str]) -> None:
    """Apaga `minio-*`/`mc-*` de outras tags (só arquivos regulares do diretório); falha vira aviso."""
    try:
        entries = list(bin_dir.iterdir())
    except OSError as exc:
        logger.warning("notislake: não foi possível listar %s para limpar tags antigas (%s)", bin_dir, exc)
        return
    for entry in entries:
        if entry.name in keep or not entry.name.startswith(tuple(f"{name}-" for name in BINARIES)):
            continue
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            entry.unlink()
        except OSError as exc:
            logger.warning("notislake: não foi possível apagar o binário antigo %s (%s)", entry.name, exc)


def install(home: Path | None = None) -> InstalledMinio:
    """Instala `minio` e `mc` em `<home>/minio/bin/<nome>-<tag>` (0755) e devolve os caminhos.

    Levanta `BinaryNotInstalledError` (pacote ausente), `BinaryIntegrityError` (divergência; nada é
    instalado), `UnsupportedPlatformError` ou `BinaryError` (manifesto inválido ou falha de escrita
    em `<home>/minio/bin`). Só reinstala o que faltar ou divergir do manifesto.
    """
    manifest = _load_manifest()
    entry = _arch_entry(manifest)
    tag = manifest["tag"]
    bin_dir = (home if home is not None else default_home()) / "minio" / "bin"
    targets = {name: bin_dir / _tag_for(name, tag) for name in BINARIES}

    wanted = [name for name in BINARIES if _sha256_file(targets[name]) != entry[name]["sha256"]]
    if wanted:
        print(f"Installing MinIO {tag}...", file=sys.stderr, flush=True)
        dist = _resolve_dist()
        try:
            bin_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _write_error(bin_dir, exc) from exc
        tarball = _find_tarball(dist, entry)
        if tarball is not None:
            try:
                with tarball.open("rb") as handle:
                    digest = _sha256_stream(handle)
            except OSError as exc:
                raise BinaryIntegrityError(f"tarball ilegível: {exc}") from exc
            _expect(digest, entry["sha256"], f"tarball {tarball.name}")
            staged = _stage_from_tarball(tarball, bin_dir, entry, wanted)
        else:
            staged = _stage_from_directory(dist, bin_dir, entry, wanted)
        try:
            for name, tmp in staged.items():
                _guard_write(bin_dir, os.replace, tmp, targets[name])
        finally:
            _discard({n: t for n, t in staged.items() if t.exists()})
        logger.info("notislake: instalado %s em %s", ", ".join(wanted), bin_dir)
        print("MinIO ready", file=sys.stderr, flush=True)

    for path in targets.values():
        if (path.stat().st_mode & 0o777) != _INSTALL_MODE:
            _guard_write(bin_dir, os.chmod, path, _INSTALL_MODE)
    _prune_other_tags(bin_dir, {path.name for path in targets.values()})
    return InstalledMinio(tag=tag, minio=targets["minio"], mc=targets["mc"])
