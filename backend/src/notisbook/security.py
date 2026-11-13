"""Token authentication for REST and WebSocket, plus Origin/Host guard for WS.

Two disjoint credentials: the UI token (whole API, `require_token`) and the per-session runtime token of a
Docker kernel (only `/api/runtime-catalog`, `require_runtime_token`); neither is accepted on the other's routes.
"""

import secrets
from dataclasses import dataclass

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


@dataclass(frozen=True)
class RuntimeGrant:
    """O que um token de runtime autoriza: pastas montadas na sessão e as raízes do warehouse do app."""

    session_id: str
    roots: tuple[str, ...]
    managed_root: str
    iceberg_root: str


class RuntimeTokens:
    """Tokens de runtime vivos, um por sessão Docker; só vivem na memória do backend."""

    def __init__(self) -> None:
        self._by_session: dict[str, tuple[str, RuntimeGrant]] = {}

    def issue(self, grant: RuntimeGrant) -> str:
        """Gera o token da sessão, invalidando o anterior (restart)."""
        token = secrets.token_urlsafe(32)
        self._by_session[grant.session_id] = (token, grant)
        return token

    def revoke(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)

    def find(self, candidate: str | None) -> RuntimeGrant | None:
        """Grant do token, comparando com todos em tempo constante (sem sair no primeiro acerto)."""
        found: RuntimeGrant | None = None
        for token, grant in list(self._by_session.values()):
            if _valid(candidate, token):
                found = grant
        return found


async def require_runtime_token(request: Request) -> RuntimeGrant:
    """FastAPI dependency das rotas de runtime: só `Authorization: Bearer <token de runtime>`; 401 caso contrário."""
    tokens: RuntimeTokens = request.app.state.kernels.runtime_tokens
    grant = tokens.find(_bearer(request.headers.get("authorization")))
    if grant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")
    return grant


async def require_runtime_host(request: Request) -> None:
    """Como `require_trusted_host`, mas aceita também o host pelo qual o container alcança o backend."""
    settings: Settings = request.app.state.settings
    if request.headers.get("host") not in settings.runtime_allowed_hosts:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden host")


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
