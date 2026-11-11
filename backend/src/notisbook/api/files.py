"""Files API: shortcuts and one-level directory listing by absolute path (metadata only)."""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .. import fs_safety
from ..files import browser, native_picker
from ..security import require_token, require_trusted_host

# Token is checked first (401), then Host (403).
router = APIRouter(prefix="/api/fs", dependencies=[Depends(require_token), Depends(require_trusted_host)])


class ChooseDirBody(BaseModel):
    default_path: str | None = None
    purpose: native_picker.Purpose = "data"


@router.post("/choose-dir")
async def choose_dir(body: ChooseDirBody | None = None) -> dict[str, Any]:
    """Open the native folder dialog; `purpose` selects a fixed prompt, `default_path` is validated."""
    default = body.default_path if body else None
    purpose = body.purpose if body else "data"
    try:
        path = await run_in_threadpool(native_picker.choose_directory, default, purpose)
    except native_picker.PickerError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"cancelled": True} if path is None else {"path": path}


@router.get("/places")
def get_places(request: Request) -> list[dict[str, str]]:
    return [asdict(p) for p in browser.places(request.app.state.store.root)]


@router.get("/list")
def list_path(
    path: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, Any]:
    try:
        return browser.list_directory(path, offset, limit)
    except browser.BrowseError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.delete("/dir", status_code=204)
async def delete_dir(path: str, request: Request) -> Response:
    """Apaga uma pasta (recursivo) ou só o symlink; a política de recusa está em `browser.check_dir_delete`."""
    state = request.app.state
    data_home = state.settings.home
    try:
        target = await run_in_threadpool(browser.check_dir_delete, path, state.store.root, data_home)
        # Sessões mudam no event loop; a checagem fica fora da threadpool.
        if state.kernels.has_session_under([target.lexical, target.real]):
            raise browser.DeleteRefused(409, "open_kernel", "A notebook is open in a running kernel under this folder")
        if not target.is_link:
            tables = await run_in_threadpool(browser.catalog_tables_overlapping, target.real, data_home)
            if tables:
                raise browser.DeleteRefused(
                    409,
                    "contains_catalog_tables",
                    "This folder is used by catalog tables",
                    tables=tables[: browser.MAX_CITED_TABLES],
                    table_count=len(tables),
                )
        await run_in_threadpool(_remove, target)
    except browser.DeleteRefused as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    return Response(status_code=204)


def _remove(target: browser.DeleteTarget) -> None:
    if target.is_link:
        try:
            target.lexical.unlink()
        except OSError as exc:
            raise browser.DeleteRefused(409, "delete_failed", "Could not remove the link") from exc
        return
    try:
        fs_safety.remove_tree(target.real)
    except fs_safety.PartialDelete as exc:
        raise browser.DeleteRefused(500, "partial_delete", str(exc)) from exc
