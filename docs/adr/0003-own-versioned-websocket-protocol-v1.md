# ADR-0003: Own versioned WebSocket protocol (v1) between UI and kernels

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

The UI must send cell executions to a kernel and stream outputs back in real time.

## Decision

The backend exposes its own protocol on `WS /api/sessions/{session_id}/channel`. Every frame is JSON with `v: 1` and a `type`. Client to server: `execute` (`cell_id`, `code`, `language`), `interrupt`, `restart`. Server to client: `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error`. A new connection replaces the previous one (close 4409); an unknown session closes with 4404. Job progress uses a separate channel, `WS /api/jobs/{job_id}/events`.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- The frontend handles a small, explicit message set instead of the full Jupyter messaging spec.
- The `v` field allows the protocol to evolve.

### Negative

- Not compatible with JupyterLab or other Jupyter frontends.

### Risks

- Client and server must change together; both validate the version and drop unknown frames.

## Validation

- **Evidence in code:** `backend/src/notisbook/kernels/protocol.py`, `backend/src/notisbook/api/sessions.py`, `frontend/src/ws/protocol.ts`, `frontend/src/ws/socket.ts`
- **How to confirm:** `grep -n 'PROTOCOL_VERSION' frontend/src/ws/protocol.ts; sed -n 1,40p backend/src/notisbook/kernels/protocol.py`

## Implementation Notes

The client reconnects with exponential backoff (8 attempts, 500 ms base, 10 s cap).

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
