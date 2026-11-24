"""Spark environment manager: installed versions, catalog, install and removal."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..kernels.service import KernelService
from ..security import require_token
from ..spark.bundles import bundle_for
from ..spark.catalog import Catalog, CatalogService, is_valid_version
from ..spark.installer import (
    InstallInProgress,
    RemoveFailed,
    SparkInstaller,
    VersionNotFound,
)
from ..spark.kernelspec import discover, kernel_name
from ..spark.packages import install_args, uninstall_args
from ..spark.requirements import core_names
from . import _packages as packages
from ._packages import AddBody, NamesBody

router = APIRouter(prefix="/api/spark", dependencies=[Depends(require_token)])


def get_installer(request: Request) -> SparkInstaller:
    return request.app.state.installer


def get_kernels(request: Request) -> KernelService:
    return request.app.state.kernels


def get_catalog(request: Request) -> CatalogService:
    return request.app.state.catalog


Catalogs = Annotated[CatalogService, Depends(get_catalog)]
Installer = Annotated[SparkInstaller, Depends(get_installer)]
Kernels = Annotated[KernelService, Depends(get_kernels)]


class InstallBody(BaseModel):
    version: str

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if not is_valid_version(value):
            raise ValueError("version must look like 3.5.9")
        return value


def _catalog_body(catalog: Catalog, installed_versions: set[str]) -> dict[str, Any]:
    return {
        "source": catalog.source,
        "fallback": catalog.fallback,
        "versions": [
            {
                "version": entry.version,
                "released_at": entry.released_at.isoformat() if entry.released_at else None,
                "line": entry.line,
                "installed": entry.version in installed_versions,
                "formats": list(bundle.formats) if (bundle := bundle_for(entry.version)) else None,
            }
            for entry in catalog.entries
        ],
    }


@router.get("/catalog")
async def get_spark_catalog(installer: Installer, catalogs: Catalogs) -> dict[str, Any]:
    installed = await asyncio.to_thread(discover, installer.base_dir)
    return _catalog_body(await catalogs.get(), {entry.version for entry in installed})


@router.get("/versions")
async def list_versions(installer: Installer, catalogs: Catalogs) -> dict[str, Any]:
    installed = await asyncio.to_thread(discover, installer.base_dir)
    catalog = await catalogs.get()
    active = installer.active_jobs()
    return {
        "installed": [entry.as_dict() for entry in installed],
        "catalog": [entry.version for entry in catalog.entries],
        "installing": [{"kernel_name": name, "job_id": job_id, "kind": kind} for name, (job_id, kind) in active.items()],
    }


@router.post("/versions", status_code=202)
async def install_version(body: InstallBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    name = kernel_name(body.version)
    if kernels.has_session(name):
        raise HTTPException(409, f"Spark {body.version} has an active kernel session")
    try:
        job = installer.start(body.version)
    except InstallInProgress as exc:
        raise HTTPException(409, f"Another job for Spark {body.version} is in progress") from exc
    return {"job_id": job.id}


@router.delete("/versions/{version}", status_code=204)
async def remove_version(version: str, installer: Installer, kernels: Kernels) -> None:
    if not is_valid_version(version):
        raise HTTPException(422, "version must look like 3.5.9")
    name = kernel_name(version)
    if kernels.has_session(name):
        raise HTTPException(409, f"Spark {version} has an active kernel session")
    try:
        removal = installer.remove(version)
    except InstallInProgress as exc:
        raise HTTPException(409, f"Another job for Spark {version} is in progress") from exc
    except VersionNotFound as exc:
        raise HTTPException(404, f"Spark {version} is not installed") from exc
    except RemoveFailed as exc:
        raise HTTPException(500, f"Could not delete: {', '.join(exc.paths)}") from exc
    try:
        await asyncio.shield(removal)
    except RemoveFailed as exc:
        raise HTTPException(500, f"Could not delete: {', '.join(exc.paths)}") from exc


def _check_version(version: str) -> None:
    if not is_valid_version(version):
        raise HTTPException(422, "version must look like 3.5.9")


@router.get("/versions/{version}/packages")
async def list_packages(version: str, installer: Installer) -> dict[str, Any]:
    _check_version(version)
    return await packages.list_packages(installer, version)


@router.post("/versions/{version}/packages", status_code=202)
async def add_packages(version: str, body: AddBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names, reqs = packages.parse_rows(body.requirements, core_names(version))
    packages.check_free(installer, kernels, version)
    pins = await packages.pins(installer, version)
    return packages.start_packages(
        installer, kernels, version, "add", lambda uv, py, url: install_args(uv, py, url, names, reqs, pins)
    )


@router.post("/versions/{version}/packages/upgrade", status_code=202)
async def upgrade_packages(version: str, body: NamesBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names = packages.parse_names(body.names, core_names(version))
    packages.check_free(installer, kernels, version)
    pins = await packages.pins(installer, version)
    return packages.start_packages(
        installer, kernels, version, "upgrade", lambda uv, py, url: install_args(uv, py, url, names, names, pins)
    )


@router.post("/versions/{version}/packages/uninstall", status_code=202)
async def uninstall_packages(version: str, body: NamesBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names = packages.parse_names(body.names, core_names(version))
    return packages.start_packages(
        installer, kernels, version, "uninstall", lambda uv, py, _url: uninstall_args(uv, py, names)
    )
