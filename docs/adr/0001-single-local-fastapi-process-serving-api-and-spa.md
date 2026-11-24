# ADR-0001: Single local FastAPI process serving the API and the SPA

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Notisbook is a desktop-style notebook application. The browser UI, the REST/WebSocket API and the management of kernels, runtimes and local storage all need a host process on the user's machine.

## Decision

The backend is one Python process: FastAPI running on uvicorn, bound to `127.0.0.1` (default port `8765`). The same process serves the compiled React SPA (`/assets` as static files plus an `index.html` catch-all for client routes) and all `/api` routes. FastAPI's generated OpenAPI/docs endpoints are disabled.

**Rationale:** The code states that the bind address is intentionally not configurable (`config.py`). The choice of FastAPI/uvicorn itself: Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- One process to install, start, stop and hand over between versions.
- UI and API share one origin, so no CORS configuration is needed.

### Negative

- Every feature (kernels, installers, MinIO supervision) shares one event loop and process lifetime.
- The app cannot be reached from another machine by design.

### Risks

- A blocking call in a handler stalls the whole app — mitigated by running installers as background jobs.

## Validation

- **Evidence in code:** `backend/src/notisbook/config.py`, `backend/src/notisbook/app.py`, `backend/src/notisbook/__main__.py`, `backend/src/notisbook/static.py`
- **How to confirm:** `grep -n 'HOST\|DEFAULT_PORT' backend/src/notisbook/config.py; grep -n 'FastAPI(' backend/src/notisbook/app.py`

## Implementation Notes

The frontend directory is resolved as `$NOTISBOOK_FRONTEND_DIST`, then `<repo>/frontend/dist`, then the packaged `_frontend` copy. A missing build returns a 503 page.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
