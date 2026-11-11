"""Token authentication for REST and WebSocket, plus Origin/Host guard for WS."""

import secrets

from fastapi import HTTPException, Request, Response, WebSocket, status

from .config import Settings

COOKIE_NAME = "notisbook_token"
WS_POLICY_VIOLATION = 1008


def _valid(candidate: str | None, expected: str) -> bool:
    if not candidate:
        return False
    return secrets.compare_digest(candidate.encode(), expected.encode())


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_token(request: Request, response: Response) -> None:
    """FastAPI dependency: Bearer header, cookie, or `?token=` (which sets the cookie)."""
    settings: Settings = request.app.state.settings
    if _valid(_bearer(request.headers.get("authorization")), settings.token):
        return
    if _valid(request.cookies.get(COOKIE_NAME), settings.token):
        return
    if _valid(request.query_params.get("token"), settings.token):
        response.set_cookie(
            COOKIE_NAME,
            settings.token,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")


async def require_trusted_host(request: Request) -> None:
    """FastAPI dependency: reject a Host header outside `allowed_hosts` (DNS-rebinding guard)."""
    settings: Settings = request.app.state.settings
    if request.headers.get("host") not in settings.allowed_hosts:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden host")


async def guard_websocket(websocket: WebSocket) -> bool:
    """Validate token, Origin and Host before `accept()`.

    On failure the handshake is refused (the server answers HTTP 403, so the
    client never sees a close code) and False is returned; callers must then
    return immediately.
    """
    settings: Settings = websocket.app.state.settings
    headers = websocket.headers
    token = (
        _bearer(headers.get("authorization"))
        or websocket.cookies.get(COOKIE_NAME)
        or websocket.query_params.get("token")
    )
    ok = (
        _valid(token, settings.token)
        and headers.get("origin") in settings.allowed_origins
        and headers.get("host") in settings.allowed_hosts
    )
    if not ok:
        await websocket.close(code=WS_POLICY_VIOLATION)
    return ok
