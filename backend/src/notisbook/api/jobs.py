"""Job status and live event stream."""

import asyncio
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from ..jobs import JobRegistry
from ..security import guard_websocket, require_token

WS_UNKNOWN_JOB = 4404

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
ws_router = APIRouter(prefix="/api")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    registry: JobRegistry = request.app.state.jobs
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.info()


@ws_router.websocket("/jobs/{job_id}/events")
async def job_events(websocket: WebSocket, job_id: str) -> None:
    if not await guard_websocket(websocket):
        return
    registry: JobRegistry = websocket.app.state.jobs
    job = registry.get(job_id)
    if job is None:
        # Accept first: closing before the handshake completes surfaces as HTTP 403.
        await websocket.accept()
        await websocket.close(code=WS_UNKNOWN_JOB)
        return
    await websocket.accept()

    async def pump() -> None:
        async for event in job.stream():
            await websocket.send_json(event.as_dict())

    async def watch_disconnect() -> None:
        # `job.stream` só acorda com um novo evento; ler o socket revela a desconexão antes disso.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass

    sender = asyncio.ensure_future(pump())
    watcher = asyncio.ensure_future(watch_disconnect())
    try:
        await asyncio.wait({sender, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if sender.done() and not sender.cancelled():
            sender.result()
            await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in (sender, watcher):
            task.cancel()
        await asyncio.gather(sender, watcher, return_exceptions=True)
