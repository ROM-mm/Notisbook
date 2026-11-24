# ADR-0021: Local access via loopback, per-startup UI token and per-session runtime tokens

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
A local web app can be reached by other pages in the browser or by DNS rebinding.

## Decision
The server binds only `127.0.0.1`. A random UI token per startup is accepted as Bearer, `notisbook_token` cookie (`HttpOnly`, `SameSite=Strict`) or `?token=`. Host and Origin are checked on trusted routes and WebSockets. Docker and DuckDB sessions get separate in-memory runtime tokens valid only on `/api/runtime-catalog` and `/iceberg`. Shutdown uses its own token from `run/backend.json`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Other local processes and web pages cannot drive the API without the token.
- A leaked runtime token cannot use the UI API.

### Negative
- The token appears in the printed URL; the access log is disabled to keep it out of stdout.

### Risks
- Some routers check the token but not the Host header (observed: contents, export, sessions, spark, duckdb, jobs).

## Validation
- **Evidence in the code:** `backend/src/notisbook/security.py`, `backend/src/notisbook/config.py`, `backend/src/notisbook/app.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`/docs`, `/redoc` and `/openapi.json` are disabled; every response carries `X-Notisbook: 1`.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
