"""Variables of a session's kernel: top-level listing and lazily loaded children."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..kernels.introspect import MAX_CHILDREN, MAX_PATH_DEPTH
from ..kernels.service import KernelService, SessionNotFound, Snapshot
from ..security import require_token, require_trusted_host
from .deps import Kernels

# Token is checked first (401), then Host (403).
router = APIRouter(prefix="/api/sessions", dependencies=[Depends(require_token), Depends(require_trusted_host)])

PATH_MAX = 2000
STEP_MAX = 256
MAX_OFFSET = 10_000_000


async def _snapshot(kernels: KernelService, session_id: str, key: str, op: Any, args: dict[str, Any]) -> Snapshot:
    try:
        session = kernels.get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, "Session not found") from exc
    return await session.introspect_variables(key, op, args)


def _parse_path(raw: str) -> list[str | int]:
    """Decode the JSON path: a non-empty list led by a variable name, then names or positions."""
    try:
        path = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(422, "Invalid path") from exc
    if not isinstance(path, list) or not 0 < len(path) <= MAX_PATH_DEPTH or not isinstance(path[0], str):
        raise HTTPException(422, "Invalid path")
    for step in path:
        valid_str = isinstance(step, str) and len(step) <= STEP_MAX
        valid_int = isinstance(step, int) and not isinstance(step, bool) and 0 <= step <= MAX_OFFSET
        if not (valid_str or valid_int):
            raise HTTPException(422, "Invalid path")
    return path


@router.get("/{session_id}/variables")
async def get_variables(session_id: str, kernels: Kernels) -> dict[str, Any]:
    snap = await _snapshot(kernels, session_id, "variables", "variables", {})
    data: dict[str, Any] = snap.data or {}
    body: dict[str, Any] = {"status": snap.status, "stale": snap.stale, "variables": data.get("variables", [])}
    for field in ("executionCount", "total", "truncated"):
        if field in data:
            body[field] = data[field]
    if snap.message:
        body["message"] = snap.message
    return body


@router.get("/{session_id}/variables/children")
async def get_children(
    session_id: str,
    kernels: Kernels,
    path: Annotated[str, Query(min_length=2, max_length=PATH_MAX)],
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_CHILDREN)] = MAX_CHILDREN,
) -> dict[str, Any]:
    steps = _parse_path(path)
    key = "children:" + json.dumps([steps, offset, limit])
    snap = await _snapshot(kernels, session_id, key, "children", {"path": steps, "offset": offset, "limit": limit})
    data: dict[str, Any] = snap.data or {}
    body: dict[str, Any] = {
        "status": snap.status,
        "stale": snap.stale,
        "children": data.get("children", []),
        "total": data.get("total", 0),
        "offset": data.get("offset", offset),
    }
    if snap.message:
        body["message"] = snap.message
    return body
