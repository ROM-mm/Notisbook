"""Raiz dos notebooks: leitura, troca persistida e token de geração contra abas/janelas obsoletas."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..kernels.service import KernelService
from ..notebooks.store import NotebookStore
from ..preferences import (
    RootRejected,
    commit_notebooks_root,
    protected_paths,
    stage_notebooks_root,
    validate_notebooks_root,
)
from ..security import require_token, require_trusted_host


class RootBody(BaseModel):
    path: str


router = APIRouter(
    prefix="/api/notebooks-root",
    dependencies=[Depends(require_token), Depends(require_trusted_host)],
)


def check_root_generation(request: Request, value: str | None) -> None:
    """409 `root_changed` se o cliente enviou uma geração diferente da atual; header ausente é aceito."""
    if value is not None and value.strip() != str(request.app.state.root_generation):
        raise HTTPException(409, "root_changed")


async def require_root_generation(
    request: Request,
    x_notisbook_root_generation: Annotated[str | None, Header()] = None,
) -> None:
    check_root_generation(request, x_notisbook_root_generation)


def _describe(request: Request) -> dict[str, Any]:
    state = request.app.state
    root = state.store.root
    return {
        "path": str(root),
        "name": root.name or "/",
        "source": state.root_source,
        "locked": state.settings.root_locked,
        "generation": state.root_generation,
    }


def _validate(raw: str, data_home: Path) -> Path:
    try:
        return validate_notebooks_root(raw, data_home)
    except RootRejected as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _prepare(resolved: Path, state: Any) -> tuple[NotebookStore, Path]:
    """I/O bloqueante: constrói o store novo e grava a preferência num temporário (nada é publicado)."""
    try:
        new_store = NotebookStore(resolved, protected_paths(state.settings.home))
    except OSError as exc:
        raise HTTPException(403, "Folder is not usable") from exc
    try:
        return new_store, stage_notebooks_root(state.settings.home, resolved)
    except OSError as exc:
        raise HTTPException(500, "Could not save the preference") from exc


@router.get("")
def get_root(request: Request) -> dict[str, Any]:
    return _describe(request)


@router.put("")
async def put_root(body: RootBody, request: Request, dry_run: bool = False) -> dict[str, Any]:
    """Troca a raiz. `dry_run=true` só valida (sem checar sessões, persistir ou trocar) e devolve `{path, name}`."""
    state = request.app.state
    if state.settings.root_locked:
        raise HTTPException(409, "locked")
    resolved = await run_in_threadpool(_validate, body.path, state.settings.home)
    if dry_run:
        return {"path": str(resolved), "name": resolved.name or "/"}
    kernels: KernelService = state.kernels
    new_store, staged = await run_in_threadpool(_prepare, resolved, state)
    # Do último check ao swap não há await: nenhuma sessão nasce no meio (o registro em
    # KernelService.create e o check de geração em POST /api/sessions também são síncronos).
    if kernels.has_any_session():
        staged.unlink(missing_ok=True)
        raise HTTPException(409, "sessions_active")
    try:
        commit_notebooks_root(state.settings.home, staged)
    except OSError as exc:
        raise HTTPException(500, "Could not save the preference") from exc
    state.store = new_store
    state.root_source = "saved"
    state.root_generation += 1
    return _describe(request)
