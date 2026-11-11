"""Kernelspecs, kernel sessions and the per-session WebSocket channel (protocol v1)."""

import asyncio
import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from ..kernels.protocol import (
    ErrorEvent,
    ExecuteRequest,
    InterruptRequest,
    RestartRequest,
    ServerEvent,
    StatusEvent,
    client_message_adapter,
)
from ..kernels.service import KernelNotFound, KernelService, SessionNotFound
from ..notebooks.store import NotebookStore, StoreError
from ..security import guard_websocket, require_token
from .notebooks_root import check_root_generation

# Application-specific close code: another connection took over the session.
WS_REPLACED = 4409
WS_UNKNOWN_SESSION = 4404


def get_kernels(request: Request) -> KernelService:
    return request.app.state.kernels


Kernels = Annotated[KernelService, Depends(get_kernels)]


class CreateSessionBody(BaseModel):
    path: str
    kernel_name: str


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
ws_router = APIRouter(prefix="/api")


@router.get("/kernelspecs")
async def list_kernelspecs(kernels: Kernels) -> list[dict[str, str]]:
    return await kernels.kernelspecs()


@router.get("/sessions")
async def list_sessions(kernels: Kernels) -> list[dict[str, str]]:
    return kernels.sessions()


@router.post("/sessions", status_code=201)
async def create_session(
    body: CreateSessionBody,
    request: Request,
    kernels: Kernels,
    x_notisbook_root_generation: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    # Geração checada aqui (não por Depends) para ficar colada ao registro da sessão: sem await
    # entre o check, o `resolve` e o registro síncrono em `kernels.create`, a troca de raiz não passa no meio.
    check_root_generation(request, x_notisbook_root_generation)
    store: NotebookStore = request.app.state.store
    try:
        target = store.resolve(body.path)
    except StoreError as exc:
        raise HTTPException(exc.status_code, str(exc) or type(exc).__name__) from exc
    cwd = target if target.is_dir() else target.parent
    # Sem await entre este check e `kernels.create`: um job de libs não começa no meio do registro da sessão.
    if request.app.state.installer.is_mutating(body.kernel_name, "packages"):
        raise HTTPException(409, "Libraries of this Spark version are being changed; try again when the job ends")
    try:
        session = await kernels.create(body.path, body.kernel_name, cwd if cwd.is_dir() else store.root, target)
    except KernelNotFound as exc:
        raise HTTPException(404, f"Kernel not found: {body.kernel_name}") from exc
    return {"session_id": session.session_id}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, kernels: Kernels) -> None:
    try:
        await kernels.delete(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, "Session not found") from exc


@ws_router.websocket("/sessions/{session_id}/channel")
async def session_channel(websocket: WebSocket, session_id: str) -> None:
    if not await guard_websocket(websocket):
        return
    kernels: KernelService = websocket.app.state.kernels
    channels: dict[str, WebSocket] = websocket.app.state.channels
    try:
        session = kernels.get(session_id)
    except SessionNotFound:
        # Accept first: closing before the handshake completes surfaces as HTTP 403.
        await websocket.accept()
        await websocket.close(code=WS_UNKNOWN_SESSION)
        return
    await websocket.accept()

    send_lock = asyncio.Lock()

    async def send(event: ServerEvent) -> None:
        async with send_lock:
            await websocket.send_json(event.model_dump(mode="json"))

    previous = channels.get(session_id)
    channels[session_id] = websocket
    session.sink = send
    if previous is not None:
        with contextlib.suppress(Exception):
            await previous.close(code=WS_REPLACED)
    await send(StatusEvent(state=session.state))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = client_message_adapter.validate_json(raw)
            except ValidationError:
                await send(ErrorEvent(code="bad_message", message="Invalid protocol v1 message"))
                continue
            if isinstance(message, ExecuteRequest):
                await session.execute(message.cell_id, message.code, message.language)
            elif isinstance(message, InterruptRequest):
                await session.interrupt()
            elif isinstance(message, RestartRequest):
                await session.restart()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if channels.get(session_id) is websocket:
            del channels[session_id]
            session.sink = None
