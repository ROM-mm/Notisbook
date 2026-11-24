"""Runtime DuckDB por versão: catálogo, extensões, libs, instalação por job e remoção."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..kernels.service import KernelService
from ..runtimes.duckdb.installer import (
    DuckDBInstaller,
    InstallInProgress,
    NotInstalled,
    UnknownVersion,
)
from ..runtimes.duckdb.kernelspec import kernel_name
from ..runtimes.duckdb.manifest import (
    Manifest,
    ManifestError,
    UnsupportedPlatform,
    is_valid_version,
    platform_key,
)
from ..security import require_token
from ..spark.installer import RemoveFailed
from ..spark.packages import install_args, uninstall_args
from . import _packages as packages
from ._packages import AddBody, NamesBody

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/duckdb", dependencies=[Depends(require_token)])


def get_installer(request: Request) -> DuckDBInstaller:
    return request.app.state.duckdb


def get_kernels(request: Request) -> KernelService:
    return request.app.state.kernels


Installer = Annotated[DuckDBInstaller, Depends(get_installer)]
Kernels = Annotated[KernelService, Depends(get_kernels)]


class InstallBody(BaseModel):
    version: str

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if not is_valid_version(value):
            raise ValueError("version must look like 2.0.1")
        return value


def _supported() -> bool:
    try:
        platform_key()
    except UnsupportedPlatform:
        return False
    return True


def _manifests(installer: DuckDBInstaller) -> dict[str, Manifest]:
    try:
        return installer.manifests()
    except ManifestError as exc:
        raise HTTPException(500, str(exc)) from exc


def _check_version(version: str) -> None:
    if not is_valid_version(version):
        raise HTTPException(422, "version must look like 2.0.1")


def _has_session(version: str, installer: DuckDBInstaller, kernels: KernelService) -> bool:
    """Sessão ativa no kernel da versão ou no `duckdb` legado que aponta para ela."""
    names = {kernel_name(version), *(e.kernel_name for e in installer.entries_of(version))}
    return any(kernels.has_session(name) for name in names)


def _extension_rows(names: tuple[str, ...], version: str, directory: Path | None) -> list[dict[str, Any]]:
    try:
        key = platform_key()
    except UnsupportedPlatform:
        key = None
    return [
        {
            "name": name,
            "installed": directory is not None
            and key is not None
            and (directory / f"v{version}" / key / f"{name}.duckdb_extension").is_file(),
        }
        for name in names
    ]


@router.get("")
async def get_status(installer: Installer) -> dict[str, Any]:
    entries = await asyncio.to_thread(installer.entries_of_all)
    try:
        manifests = installer.manifests()
    except ManifestError:
        log.warning("DuckDB extension manifest is unreadable", exc_info=True)
        manifests = {}
    have = {entry.version for entry in entries}
    return {
        "supported": _supported(),
        "catalog": [
            {"version": version, "installed": version in have, "extensions": list(manifest.names)}
            for version, manifest in manifests.items()
        ],
        "installed": [entry.as_dict() for entry in entries],
        "installing": [
            {"kernel_name": name, "job_id": job_id, "kind": kind}
            for name, (job_id, kind) in installer.active_jobs().items()
            if kind != "remove"
        ],
    }


@router.get("/versions/{version}/extensions")
async def list_extensions(version: str, installer: Installer) -> dict[str, Any]:
    _check_version(version)
    entries = await asyncio.to_thread(installer.entries_of, version)
    if entries:
        # O runtime instalado manda: o manifesto pode ter mudado depois da instalação.
        entry = entries[0]
        return {
            "version": version,
            "extensions": _extension_rows(entry.extensions, version, entry.extension_directory),
        }
    manifest = _manifests(installer).get(version)
    if manifest is None:
        raise HTTPException(404, f"DuckDB {version} is not installed and is not in the manifest")
    return {"version": version, "extensions": _extension_rows(manifest.names, version, None)}


@router.post("/versions", status_code=202)
async def install_version(body: InstallBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    if not _supported():
        raise HTTPException(422, "DuckDB runtime is not available on this platform")
    if body.version not in _manifests(installer):
        raise HTTPException(422, f"DuckDB {body.version} is not in the extension manifest")
    if _has_session(body.version, installer, kernels):
        raise HTTPException(409, f"DuckDB {body.version} has an active kernel session")
    try:
        job = installer.start(body.version)
    except InstallInProgress as exc:
        raise HTTPException(409, f"Another job for DuckDB {body.version} is in progress") from exc
    except UnknownVersion as exc:
        raise HTTPException(422, f"DuckDB {body.version} is not in the extension manifest") from exc
    return {"job_id": job.id}


@router.delete("/versions/{version}", status_code=204)
async def remove_version(version: str, installer: Installer, kernels: Kernels) -> None:
    _check_version(version)
    if _has_session(version, installer, kernels):
        raise HTTPException(409, f"DuckDB {version} has an active kernel session")
    try:
        removal = installer.remove(version)
    except InstallInProgress as exc:
        raise HTTPException(409, f"Another job for DuckDB {version} is in progress") from exc
    except NotInstalled as exc:
        raise HTTPException(404, f"DuckDB {version} is not installed") from exc
    except RemoveFailed as exc:
        raise HTTPException(500, f"Could not delete: {', '.join(exc.paths)}") from exc
    try:
        await asyncio.shield(removal)
    except RemoveFailed as exc:
        raise HTTPException(500, f"Could not delete: {', '.join(exc.paths)}") from exc


@router.get("/versions/{version}/packages")
async def list_packages(version: str, installer: Installer) -> dict[str, Any]:
    _check_version(version)
    return await packages.list_packages(installer, version)


@router.post("/versions/{version}/packages", status_code=202)
async def add_packages(version: str, body: AddBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names, reqs = packages.parse_rows(body.requirements, installer.core_names(version))
    packages.check_free(installer, kernels, version)
    pins = await packages.pins(installer, version)
    return packages.start_packages(
        installer, kernels, version, "add", lambda uv, py, url: install_args(uv, py, url, names, reqs, pins)
    )


@router.post("/versions/{version}/packages/upgrade", status_code=202)
async def upgrade_packages(version: str, body: NamesBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names = packages.parse_names(body.names, installer.core_names(version))
    packages.check_free(installer, kernels, version)
    pins = await packages.pins(installer, version)
    return packages.start_packages(
        installer, kernels, version, "upgrade", lambda uv, py, url: install_args(uv, py, url, names, names, pins)
    )


@router.post("/versions/{version}/packages/uninstall", status_code=202)
async def uninstall_packages(version: str, body: NamesBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names = packages.parse_names(body.names, installer.core_names(version))
    return packages.start_packages(
        installer, kernels, version, "uninstall", lambda uv, py, _url: uninstall_args(uv, py, names)
    )
