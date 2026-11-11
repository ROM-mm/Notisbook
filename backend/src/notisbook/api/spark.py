"""Spark environment manager: installed versions, catalog, install and removal."""

import asyncio
import logging
import shutil
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from packaging.utils import canonicalize_name
from pydantic import BaseModel, Field, field_validator

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
from ..spark.packages import (
    PackagesError,
    UvNotFound,
    core_pins,
    install_args,
    list_installed,
    uninstall_args,
)
from ..spark.requirements import core_names, parse_requirement, validate_name

log = logging.getLogger(__name__)
MAX_ROWS = 50
MAX_NAMES = 500

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


class RequirementRow(BaseModel):
    name: str
    spec: str = ""


class AddBody(BaseModel):
    requirements: list[RequirementRow] = Field(min_length=1, max_length=MAX_ROWS)


class NamesBody(BaseModel):
    names: list[str] = Field(min_length=1, max_length=MAX_NAMES)


def _invalid(errors: list[dict[str, Any]]) -> HTTPException:
    return HTTPException(422, detail=errors)


def _protected(value: str) -> str:
    return f'"{value}" is protected: remove and reinstall the environment to change it'


def _parse_rows(rows: list[RequirementRow], core: set[str]) -> tuple[list[str], list[str]]:
    """Canonical names and requirement strings; 422 with per-row errors for invalid or repeated names."""
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    names: list[str] = []
    reqs: list[str] = []
    for index, row in enumerate(rows):
        try:
            req = parse_requirement(row.name, row.spec)
        except ValueError as exc:
            field = "name" if str(exc).startswith("invalid library name") else "spec"
            errors.append({"loc": ["body", "requirements", index, field], "msg": str(exc)})
            continue
        canonical = validate_name(row.name)
        if canonical in core:
            errors.append({"loc": ["body", "requirements", index, "name"], "msg": _protected(row.name)})
            continue
        if canonical in seen:
            errors.append({"loc": ["body", "requirements", index, "name"], "msg": f'"{row.name}" is already in the list.'})
            continue
        seen.add(canonical)
        names.append(canonical)
        reqs.append(req)
    if errors:
        raise _invalid(errors)
    return names, reqs


def _parse_names(raw: list[str], core: set[str]) -> list[str]:
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    names: list[str] = []
    for index, value in enumerate(raw):
        try:
            canonical = validate_name(value)
        except ValueError as exc:
            errors.append({"loc": ["body", "names", index], "msg": str(exc)})
            continue
        if canonical in core:
            errors.append({"loc": ["body", "names", index], "msg": _protected(value)})
            continue
        if canonical in seen:
            errors.append({"loc": ["body", "names", index], "msg": f'"{value}" is already in the list.'})
            continue
        seen.add(canonical)
        names.append(canonical)
    if errors:
        raise _invalid(errors)
    return names


def _catalog_body(catalog: Catalog, installed_versions: set[str]) -> dict[str, Any]:
    return {
        "source": catalog.source,
        "fallback": catalog.fallback,
        "versions": [
            {
                "version": entry.version,
                "released_at": entry.released_at.isoformat() if entry.released_at else None,
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
    installed = await asyncio.to_thread(discover, installer.base_dir)
    entry = next((e for e in installed if e.version == version), None)
    if entry is None:
        raise HTTPException(404, f"Spark {version} is not installed")
    uv = shutil.which("uv")
    if uv is None:
        raise HTTPException(503, "uv not found; install it with: brew install uv")
    try:
        items = await list_installed(uv, entry.env_dir, installer.packages_env())
    except PackagesError as exc:
        log.warning("listing libs of Spark %s failed: %s", version, exc)
        raise HTTPException(500, str(exc)) from exc
    core = core_names(version)
    items = [item for item in items if str(canonicalize_name(item["name"])) not in core]
    held = installer.active_jobs().get(entry.kernel_name)
    return {
        "version": version,
        "kernel_name": entry.kernel_name,
        "env_dir": str(entry.env_dir),
        "job_id": held[0] if held else None,
        "job_action": installer.package_action(entry.kernel_name),
        "packages": items,
    }


async def _pins(version: str, installer: SparkInstaller) -> list[str]:
    """Pins das libs base nas versões atuais; vazio se a versão não estiver instalada ou sem `uv`.

    Falha ao listar o ambiente (`PackagesError`) vira 500.
    """
    entry = next((e for e in await asyncio.to_thread(discover, installer.base_dir) if e.version == version), None)
    uv = shutil.which("uv")
    if entry is None or uv is None:
        return []
    try:
        items = await list_installed(uv, entry.env_dir, installer.packages_env())
    except PackagesError as exc:
        raise HTTPException(500, f"Cannot pin core libraries: {exc}") from exc
    return core_pins(items, core_names(version))


def _check_free(version: str, installer: SparkInstaller, kernels: KernelService) -> None:
    """409 antes de `_pins` (que roda `uv pip list`); `_start_packages` repete a checagem junto do lock."""
    if kernels.has_session(kernel_name(version)):
        raise HTTPException(409, f"Spark {version} has an active kernel session")
    if installer.is_mutating(kernel_name(version)):
        raise HTTPException(409, f"Another job for Spark {version} is in progress")


def _start_packages(
    version: str,
    action: str,
    builder: Callable[[str, str, str], list[str]],
    installer: SparkInstaller,
    kernels: KernelService,
) -> dict[str, str]:
    """Sync on purpose: the session check and the lock acquisition have no await in between."""
    if kernels.has_session(kernel_name(version)):
        raise HTTPException(409, f"Spark {version} has an active kernel session")
    try:
        job = installer.start_packages(version, action, builder)
    except InstallInProgress as exc:
        raise HTTPException(409, f"Another job for Spark {version} is in progress") from exc
    except VersionNotFound as exc:
        raise HTTPException(404, f"Spark {version} is not installed") from exc
    except UvNotFound as exc:
        raise HTTPException(503, "uv not found; install it with: brew install uv") from exc
    return {"job_id": job.id}


@router.post("/versions/{version}/packages", status_code=202)
async def add_packages(version: str, body: AddBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names, reqs = _parse_rows(body.requirements, core_names(version))
    _check_free(version, installer, kernels)
    pins = await _pins(version, installer)
    return _start_packages(
        version, "add", lambda uv, py, url: install_args(uv, py, url, names, reqs, pins), installer, kernels
    )


@router.post("/versions/{version}/packages/upgrade", status_code=202)
async def upgrade_packages(version: str, body: NamesBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names = _parse_names(body.names, core_names(version))
    _check_free(version, installer, kernels)
    pins = await _pins(version, installer)
    return _start_packages(
        version, "upgrade", lambda uv, py, url: install_args(uv, py, url, names, names, pins), installer, kernels
    )


@router.post("/versions/{version}/packages/uninstall", status_code=202)
async def uninstall_packages(version: str, body: NamesBody, installer: Installer, kernels: Kernels) -> dict[str, str]:
    _check_version(version)
    names = _parse_names(body.names, core_names(version))
    return _start_packages(version, "uninstall", lambda uv, py, _url: uninstall_args(uv, py, names), installer, kernels)
