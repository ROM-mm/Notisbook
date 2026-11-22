"""Runtime DuckDB: status, extensões, instalação por job e remoção."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..kernels.service import KernelService
from ..runtimes.duckdb.installer import DuckDBInstaller, InstallInProgress, NotInstalled
from ..runtimes.duckdb.kernelspec import KERNEL_NAME
from ..runtimes.duckdb.manifest import (
    ManifestError,
    UnsupportedPlatform,
    load_manifest,
    platform_key,
)
from ..security import require_token
from ..spark.installer import RemoveFailed

router = APIRouter(prefix="/api/duckdb", dependencies=[Depends(require_token)])


def get_installer(request: Request) -> DuckDBInstaller:
    return request.app.state.duckdb


def get_kernels(request: Request) -> KernelService:
    return request.app.state.kernels


Installer = Annotated[DuckDBInstaller, Depends(get_installer)]
Kernels = Annotated[KernelService, Depends(get_kernels)]


def _supported() -> bool:
    try:
        platform_key()
    except UnsupportedPlatform:
        return False
    return True


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
    entry = await asyncio.to_thread(lambda: _find(installer))
    active = installer.active_job()
    try:
        version: str | None = load_manifest().duckdb_version
    except ManifestError:
        version = None
    return {
        "kernel_name": KERNEL_NAME,
        "supported": _supported(),
        "version": version,
        "installed": entry.as_dict() if entry else None,
        "installing": {"job_id": active[0], "kind": active[1]} if active else None,
    }


def _find(installer: DuckDBInstaller) -> Any:
    try:
        return installer.find()
    except NotInstalled:
        return None


@router.get("/extensions")
async def list_extensions(installer: Installer) -> dict[str, Any]:
    try:
        manifest = load_manifest()
    except ManifestError as exc:
        raise HTTPException(500, str(exc)) from exc
    entry = await asyncio.to_thread(lambda: _find(installer))
    directory = entry.extension_directory if entry else None
    return {
        "version": manifest.duckdb_version,
        "extensions": _extension_rows(manifest.names, manifest.duckdb_version, directory),
    }


@router.post("/install", status_code=202)
async def install(installer: Installer, kernels: Kernels) -> dict[str, str]:
    if not _supported():
        raise HTTPException(422, "DuckDB runtime is not available on this platform")
    if kernels.has_session(KERNEL_NAME):
        raise HTTPException(409, "The DuckDB runtime has an active kernel session")
    try:
        job = installer.start()
    except InstallInProgress as exc:
        raise HTTPException(409, "Another DuckDB job is in progress") from exc
    return {"job_id": job.id}


@router.delete("", status_code=204)
async def remove(installer: Installer, kernels: Kernels) -> None:
    if kernels.has_session(KERNEL_NAME):
        raise HTTPException(409, "The DuckDB runtime has an active kernel session")
    try:
        removal = installer.remove()
    except InstallInProgress as exc:
        raise HTTPException(409, "Another DuckDB job is in progress") from exc
    except NotInstalled as exc:
        raise HTTPException(404, "The DuckDB runtime is not installed") from exc
    except RemoveFailed as exc:
        raise HTTPException(500, f"Could not delete: {', '.join(exc.paths)}") from exc
    try:
        await asyncio.shield(removal)
    except RemoveFailed as exc:
        raise HTTPException(500, f"Could not delete: {', '.join(exc.paths)}") from exc
