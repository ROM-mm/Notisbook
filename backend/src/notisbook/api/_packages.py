"""Libs routes shared by the managed environments (Spark and DuckDB): parsing, 409/404/503 rules and responses."""

import asyncio
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from fastapi import HTTPException
from packaging.utils import canonicalize_name
from pydantic import BaseModel, Field

from ..jobs import Job
from ..kernels.service import KernelService
from ..spark.installer import InstallInProgress, VersionNotFound
from ..spark.packages import (
    PackagesError,
    UvNotFound,
    core_pins,
    list_installed,
)
from ..spark.requirements import parse_requirement, validate_name

log = logging.getLogger(__name__)
MAX_ROWS = 50
MAX_NAMES = 500


class ManagedEnv(Protocol):
    """What the libs routes need from an installer of versioned environments."""

    label: str
    base_dir: Path

    def find(self, version: str) -> Any: ...  # entry with `kernel_name` and `env_dir`; raises VersionNotFound

    def lock_name(self, version: str, entry: Any = None) -> str: ...

    def session_names(self, version: str) -> set[str]: ...

    def core_names(self, version: str) -> set[str]: ...

    def is_mutating(self, name: str, kind: str | None = None) -> bool: ...

    def active_jobs(self) -> dict[str, tuple[str, str]]: ...

    def package_action(self, name: str) -> str | None: ...

    def packages_env(self) -> dict[str, str]: ...

    def start_packages(
        self, version: str, action: str, argv_builder: Callable[[str, str, str], list[str]]
    ) -> Job: ...


class RequirementRow(BaseModel):
    name: str
    spec: str = ""


class AddBody(BaseModel):
    requirements: list[RequirementRow] = Field(min_length=1, max_length=MAX_ROWS)


class NamesBody(BaseModel):
    names: list[str] = Field(min_length=1, max_length=MAX_NAMES)


def invalid(errors: list[dict[str, Any]]) -> HTTPException:
    return HTTPException(422, detail=errors)


def protected(value: str) -> str:
    return f'"{value}" is protected: remove and reinstall the runtime to change it'


def parse_rows(rows: list[RequirementRow], core: set[str]) -> tuple[list[str], list[str]]:
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
            errors.append({"loc": ["body", "requirements", index, "name"], "msg": protected(row.name)})
            continue
        if canonical in seen:
            errors.append({"loc": ["body", "requirements", index, "name"], "msg": f'"{row.name}" is already in the list.'})
            continue
        seen.add(canonical)
        names.append(canonical)
        reqs.append(req)
    if errors:
        raise invalid(errors)
    return names, reqs


def parse_names(raw: list[str], core: set[str]) -> list[str]:
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
            errors.append({"loc": ["body", "names", index], "msg": protected(value)})
            continue
        if canonical in seen:
            errors.append({"loc": ["body", "names", index], "msg": f'"{value}" is already in the list.'})
            continue
        seen.add(canonical)
        names.append(canonical)
    if errors:
        raise invalid(errors)
    return names


async def pins(installer: ManagedEnv, version: str) -> list[str]:
    """Pins das libs base nas versões atuais; vazio se a versão não estiver instalada ou sem `uv`.

    Falha ao listar o ambiente (`PackagesError`) vira 500.
    """
    try:
        entry = await asyncio.to_thread(installer.find, version)
    except VersionNotFound:
        return []
    uv = shutil.which("uv")
    if uv is None:
        return []
    try:
        items = await list_installed(uv, entry.env_dir, installer.packages_env())
    except PackagesError as exc:
        raise HTTPException(500, f"Cannot pin core libraries: {exc}") from exc
    return core_pins(items, installer.core_names(version))


def check_free(installer: ManagedEnv, kernels: KernelService, version: str) -> None:
    """409 antes de `pins` (que roda `uv pip list`); `start_packages` repete a checagem junto do lock."""
    if any(kernels.has_session(name) for name in installer.session_names(version)):
        raise HTTPException(409, f"{installer.label} {version} has an active kernel session")
    if installer.is_mutating(installer.lock_name(version)):
        raise HTTPException(409, f"Another job for {installer.label} {version} is in progress")


def start_packages(
    installer: ManagedEnv,
    kernels: KernelService,
    version: str,
    action: str,
    builder: Callable[[str, str, str], list[str]],
) -> dict[str, str]:
    """Sync on purpose: the session check and the lock acquisition have no await in between."""
    if any(kernels.has_session(name) for name in installer.session_names(version)):
        raise HTTPException(409, f"{installer.label} {version} has an active kernel session")
    try:
        job = installer.start_packages(version, action, builder)
    except InstallInProgress as exc:
        raise HTTPException(409, f"Another job for {installer.label} {version} is in progress") from exc
    except VersionNotFound as exc:
        raise HTTPException(404, f"{installer.label} {version} is not installed") from exc
    except UvNotFound as exc:
        raise HTTPException(503, "uv not found; install it with: brew install uv") from exc
    return {"job_id": job.id}


async def list_packages(installer: ManagedEnv, version: str) -> dict[str, Any]:
    """Libs of the installed version, without the protected ones, plus the job holding its lock."""
    try:
        entry = await asyncio.to_thread(installer.find, version)
    except VersionNotFound as exc:
        raise HTTPException(404, f"{installer.label} {version} is not installed") from exc
    uv = shutil.which("uv")
    if uv is None:
        raise HTTPException(503, "uv not found; install it with: brew install uv")
    try:
        items = await list_installed(uv, entry.env_dir, installer.packages_env())
    except PackagesError as exc:
        log.warning("listing libs of %s %s failed: %s", installer.label, version, exc)
        raise HTTPException(500, str(exc)) from exc
    core = installer.core_names(version)
    items = [item for item in items if str(canonicalize_name(item["name"])) not in core]
    name = installer.lock_name(version, entry)
    held = installer.active_jobs().get(name)
    return {
        "version": version,
        "kernel_name": entry.kernel_name,
        "env_dir": str(entry.env_dir),
        "job_id": held[0] if held else None,
        "job_action": installer.package_action(name),
        "packages": items,
    }
