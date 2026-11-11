"""Contents API: list, read, save, create, rename and delete notebooks under the root."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..kernels.service import KernelService
from ..notebooks.store import NotebookStore, StoreError
from ..security import require_token
from .notebooks_root import require_root_generation


def get_store(request: Request) -> NotebookStore:
    return request.app.state.store


Store = Annotated[NotebookStore, Depends(get_store)]

OPEN_KERNEL_MESSAGE = "Notebook is open in a running kernel"


def get_kernels(request: Request) -> KernelService:
    return request.app.state.kernels


Kernels = Annotated[KernelService, Depends(get_kernels)]


def _http(exc: StoreError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc) or type(exc).__name__)


class CreateBody(BaseModel):
    type: Literal["notebook", "directory"] = "notebook"


class RenameBody(BaseModel):
    new_path: str


router = APIRouter(prefix="/api/contents", dependencies=[Depends(require_token)])
Guard = [Depends(require_root_generation)]


@router.get("")
def list_contents(store: Store, path: str = "") -> list[dict[str, Any]]:
    try:
        return [e.to_dict() for e in store.list_dir(path)]
    except StoreError as exc:
        raise _http(exc) from exc


@router.get("/{path:path}")
def read_notebook(path: str, store: Store) -> Any:
    try:
        return store.read_notebook(path)
    except StoreError as exc:
        raise _http(exc) from exc


@router.put("/{path:path}", dependencies=Guard)
def save_notebook(path: str, store: Store, notebook: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    try:
        return store.write_notebook(path, notebook).to_dict()
    except StoreError as exc:
        raise _http(exc) from exc


@router.post("/{path:path}", status_code=201, dependencies=Guard)
def create_item(path: str, store: Store, body: CreateBody | None = None) -> dict[str, Any]:
    try:
        return store.create(path, (body or CreateBody()).type).to_dict()
    except StoreError as exc:
        raise _http(exc) from exc


@router.patch("/{path:path}", dependencies=Guard)
async def rename_item(path: str, body: RenameBody, store: Store, kernels: Kernels) -> dict[str, Any]:
    # Checagem de sessões no event loop (onde `_sessions` muda); só o I/O vai para a threadpool.
    try:
        blocked = kernels.has_session_under(store.blocking_paths(path))
    except StoreError as exc:
        raise _http(exc) from exc
    if blocked:
        raise HTTPException(409, OPEN_KERNEL_MESSAGE)
    try:
        return (await run_in_threadpool(store.rename, path, body.new_path)).to_dict()
    except StoreError as exc:
        raise _http(exc) from exc


@router.delete("/{path:path}", status_code=204, dependencies=Guard)
async def delete_item(path: str, store: Store, kernels: Kernels) -> Response:
    try:
        blocked = kernels.has_session_under(store.blocking_paths(path))
    except StoreError as exc:
        raise _http(exc) from exc
    if blocked:
        raise HTTPException(409, OPEN_KERNEL_MESSAGE)
    try:
        await run_in_threadpool(store.delete, path)
    except StoreError as exc:
        raise _http(exc) from exc
    return Response(status_code=204)
