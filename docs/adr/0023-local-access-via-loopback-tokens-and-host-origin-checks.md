# ADR-0023: Local access via loopback, separate tokens and Host/Origin checks

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

A local web server can be reached by other local processes and by malicious web pages (DNS rebinding).

## Decision

The server binds only to `127.0.0.1`. The UI token is random per process and accepted as Bearer, cookie `notisbook_token` or `?token=` (which sets an `HttpOnly; SameSite=Strict` cookie). Docker and DuckDB kernels use separate per-session runtime tokens, valid only on runtime routes; shutdown uses a third token. Host headers are checked against an allow-list, and WebSockets also require an allowed `Origin`. No CORS middleware is configured. The access log is disabled.

**Rationale:** The code states that the access log is disabled because the token travels in the URL.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Credentials are scoped to their purpose.
- Protects against cross-site and DNS-rebinding requests.

### Negative

- Some routers check only the token, not the Host header.

### Risks

- The local MinIO credentials are returned to the authenticated UI by `GET /api/notislake/local/credentials`.

## Validation

- **Evidence in code:** `backend/src/notisbook/security.py`, `backend/src/notisbook/config.py`, `backend/src/notisbook/api/lifecycle.py`, `frontend/src/api/auth.ts`
- **How to confirm:** `sed -n 1,40p backend/src/notisbook/security.py`

## Implementation Notes

The frontend keeps the token in memory only and removes it from the URL after bootstrap.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
