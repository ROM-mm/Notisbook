"""Serves the built frontend (`frontend/dist`) with SPA fallback and CSP."""

from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

# `style-src 'unsafe-inline'` is required by CodeMirror's runtime-injected styles and the
# `<style>` blocks inside the Shadow DOM of HTML outputs; scripts stay `'self'` only.
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; connect-src 'self'; script-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; object-src 'none'"
)
_HTML_HEADERS = {"Content-Security-Policy": CSP}


def _missing_build_page(dist: Path) -> HTMLResponse:
    body = (
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Notisbook</title>"
        "<h1>Frontend not built</h1>"
        f"<p>There is no <code>index.html</code> in <code>{escape(str(dist))}</code>.</p>"
        "<p>Run <code>./start.sh</code> (or <code>npm --prefix frontend run build</code>) "
        "and restart.</p></html>"
    )
    return HTMLResponse(body, status_code=503, headers=_HTML_HEADERS)


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Register `/assets` and the SPA fallback. Must run after all `/api` routers."""
    dist = dist.resolve()
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # Pages are public on purpose: the SPA authenticates through `?token=` -> cookie.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        if not index.is_file():
            return _missing_build_page(dist)
        candidate = (dist / path).resolve()
        if path and candidate.is_relative_to(dist) and candidate.is_file() and candidate != index:
            return FileResponse(candidate)
        return FileResponse(index, headers=_HTML_HEADERS)
