"""System endpoints."""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil
from fastapi import APIRouter, Depends, Request, WebSocket

from ..security import guard_websocket, require_token, require_trusted_host
from ..spark.prereqs import check_prereqs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Arma o contador: cpu_percent(interval=None) compara com a chamada anterior e a primeira devolve 0.0.
psutil.cpu_percent(interval=None)


def _safe(collect: Callable[[], dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Falha de uma métrica vira `null` sem derrubar as demais."""
    try:
        return collect()
    except Exception:
        logger.warning("system resources: %s unavailable", name, exc_info=True)
        return None


def _memory() -> dict[str, Any]:
    mem = psutil.virtual_memory()
    return {"used": int(mem.total - mem.available), "total": int(mem.total)}


def _cpu() -> dict[str, Any]:
    return {"percent": float(psutil.cpu_percent(interval=None)), "cores": os.cpu_count() or 1}


def _disk(root: Path) -> dict[str, Any]:
    try:
        usage = psutil.disk_usage(str(root))
    except OSError:
        usage = psutil.disk_usage(str(Path.home()))
    return {"used": int(usage.total - usage.free), "total": int(usage.total)}


@router.get("/health", dependencies=[Depends(require_token)])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system/prereqs", dependencies=[Depends(require_token)])
async def prereqs() -> dict[str, Any]:
    return (await check_prereqs()).as_dict()


@router.get("/system/resources", dependencies=[Depends(require_token), Depends(require_trusted_host)])
def resources(request: Request) -> dict[str, Any]:
    root: Path = request.app.state.store.root
    return {
        "memory": _safe(_memory, "memory"),
        "cpu": _safe(_cpu, "cpu"),
        "disk": _safe(lambda: _disk(root), "disk"),
    }


@router.websocket("/ws/ping")
async def ws_ping(websocket: WebSocket) -> None:
    if not await guard_websocket(websocket):
        return
    await websocket.accept()
    await websocket.send_text("pong")
    await websocket.close()
