"""Manifesto das extensões DuckDB: versão fixa e sha256 por plataforma (`extensions.json`)."""

import json
import platform
import re
from dataclasses import dataclass
from pathlib import Path

from ...platform_support import is_apple_silicon

MANIFEST_PATH = Path(__file__).with_name("extensions.json")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9_]*")
_ARM64_KEY = "osx_arm64"


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


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw["duckdb"]
        base_url = raw["base_url"].rstrip("/")
        parsed: dict[str, dict[str, Digests]] = {}
        for name, plats in raw["extensions"].items():
            if not _NAME.fullmatch(name):
                raise ManifestError(f"invalid extension name {name!r}")
            parsed[name] = {key: Digests(d["sha256_gz"], d["sha256_ext"]) for key, d in plats.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ManifestError(f"cannot read extension manifest {path.name}: {exc}") from exc
    if not base_url.startswith("https://") or not isinstance(version, str) or not parsed:
        raise ManifestError("manifest needs a DuckDB version, an https base_url and extensions")
    platforms = {frozenset(plats) for plats in parsed.values()}
    if len(platforms) != 1 or not next(iter(platforms)):
        raise ManifestError("every extension must cover the same, non-empty set of platforms")
    for name, plats in parsed.items():
        for key, digests in plats.items():
            if not (_SHA256.fullmatch(digests.sha256_gz) and _SHA256.fullmatch(digests.sha256_ext)):
                raise ManifestError(f"invalid sha256 for {name} on {key}")
    return Manifest(version, base_url, parsed)
