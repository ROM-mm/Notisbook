"""Export API: convert the notebook sent in the request body into a downloadable file.

Stateless by design: nothing is read from or written to disk, and `filename` only
names the download.
"""

import logging
import time
from typing import Annotated, Any, Literal
from urllib.parse import quote

import nbformat
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError

from ..export.common import download_name, validate_notebook
from ..export.html_report import to_html_report
from ..export.py_source import to_databricks_py
from ..notebooks.store import StoreError
from ..security import require_token

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 50 * 1024 * 1024
ExportFormat = Literal["py", "ipynb", "html"]
CONTENT_TYPES: dict[str, str] = {
    "py": "text/x-python; charset=utf-8",
    "ipynb": "application/x-ipynb+json",
    "html": "text/html; charset=utf-8",
}


class ExportBody(BaseModel):
    notebook: dict[str, Any]
    filename: str = ""


def _too_large() -> HTTPException:
    return HTTPException(413, f"Notebook exceeds {MAX_BODY_BYTES // (1024 * 1024)} MB")


async def read_limited_body(request: Request) -> bytes:
    """Read the request body, answering 413 before buffering more than `MAX_BODY_BYTES`."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise _too_large()
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _content_disposition(name: str) -> str:
    ascii_name = "".join(c if c.isascii() and c.isprintable() and c != "%" else "_" for c in name)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


def _render(fmt: str, nb: Any, filename: str) -> bytes:
    if fmt == "py":
        return to_databricks_py(nb)
    if fmt == "html":
        return to_html_report(nb, filename)
    return nbformat.writes(nb).encode("utf-8")


router = APIRouter(prefix="/api/export", dependencies=[Depends(require_token)])


@router.post("/{fmt}")
def export_notebook(fmt: ExportFormat, raw: Annotated[bytes, Depends(read_limited_body)]) -> Response:
    started = time.perf_counter()
    try:
        body = ExportBody.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid export request body") from exc
    try:
        nb = validate_notebook(body.notebook)
    except StoreError as exc:
        raise HTTPException(exc.status_code, str(exc) or type(exc).__name__) from exc
    content = _render(fmt, nb, body.filename)
    headers = {
        "Content-Type": CONTENT_TYPES[fmt],
        "Content-Disposition": _content_disposition(download_name(body.filename, fmt)),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if fmt == "html":
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    logger.info("export format=%s bytes=%d ms=%d", fmt, len(content), (time.perf_counter() - started) * 1000)
    return Response(content=content, headers=headers)
