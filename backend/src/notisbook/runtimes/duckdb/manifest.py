"""Manifesto das extensões DuckDB: sha256 por versão e plataforma (`extensions.json`)."""

import json
import platform
import re
from dataclasses import dataclass
from pathlib import Path

from ...platform_support import is_apple_silicon

MANIFEST_PATH = Path(__file__).with_name("extensions.json")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9_]*")
# fullmatch + ASCII: a versão entra em caminho, URL e requisito pip.
_VERSION = re.compile(r"\d+\.\d+\.\d+", re.ASCII)
_ARM64_KEY = "osx_arm64"


def is_valid_version(version: str) -> bool:
    return _VERSION.fullmatch(version) is not None


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class ManifestError(Exception):
    """Manifesto ilegível ou inconsistente; a instalação não deve prosseguir."""


class UnsupportedPlatform(Exception):
    """Sem extensões publicadas no manifesto para este sistema/arquitetura."""


@dataclass(frozen=True)
class Digests:
    sha256_gz: str
    sha256_ext: str


@dataclass(frozen=True)
class Manifest:
    duckdb_version: str
    base_url: str
    # extensão -> plataforma -> hashes do arquivo baixado (.gz) e do .duckdb_extension descompactado
    extensions: dict[str, dict[str, Digests]]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.extensions)

    def url(self, platform_key: str, name: str) -> str:
        return f"{self.base_url}/v{self.duckdb_version}/{platform_key}/{name}.duckdb_extension.gz"

    def digests(self, platform_key: str, name: str) -> Digests:
        return self.extensions[name][platform_key]


def platform_key() -> str:
    """Plataforma DuckDB do host (osx_arm64, inclusive sob Rosetta); levanta UnsupportedPlatform nas demais."""
    if is_apple_silicon():
        return _ARM64_KEY
    raise UnsupportedPlatform(f"{platform.system()} {platform.machine()}")


def _parse_version(version: str, raw: object, base_url: str) -> Manifest:
    if not is_valid_version(version) or not isinstance(raw, dict):
        raise ManifestError(f"invalid DuckDB version entry {version!r}")
    parsed: dict[str, dict[str, Digests]] = {}
    for name, plats in raw["extensions"].items():
        if not _NAME.fullmatch(name):
            raise ManifestError(f"invalid extension name {name!r}")
        parsed[name] = {key: Digests(d["sha256_gz"], d["sha256_ext"]) for key, d in plats.items()}
    if not parsed:
        raise ManifestError(f"DuckDB {version} has no extensions")
    platforms = {frozenset(plats) for plats in parsed.values()}
    if len(platforms) != 1 or not next(iter(platforms)):
        raise ManifestError(f"every extension of DuckDB {version} must cover the same, non-empty set of platforms")
    for name, plats in parsed.items():
        for key, digests in plats.items():
            if not (_SHA256.fullmatch(digests.sha256_gz) and _SHA256.fullmatch(digests.sha256_ext)):
                raise ManifestError(f"invalid sha256 for {name} on {key} (DuckDB {version})")
    return Manifest(version, base_url, parsed)


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Manifest]:
    """Manifestos por versão do DuckDB, da mais nova para a mais antiga."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        base_url = raw["base_url"].rstrip("/")
        if not base_url.startswith("https://"):
            raise ManifestError("manifest needs an https base_url")
        versions = {v: _parse_version(v, entry, base_url) for v, entry in raw["versions"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ManifestError(f"cannot read extension manifest {path.name}: {exc}") from exc
    if not versions:
        raise ManifestError("manifest needs at least one DuckDB version")
    return {v: versions[v] for v in sorted(versions, key=version_key, reverse=True)}
