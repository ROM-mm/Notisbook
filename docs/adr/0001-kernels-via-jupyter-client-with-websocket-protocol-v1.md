# ADR-0001: Kernels via jupyter_client with a custom WebSocket protocol (v1)

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
The browser UI must run cells in Jupyter kernels of different runtimes and receive outputs in real time, while the backend controls sessions, languages and limits.

## Decision
The backend is the only module that talks to kernels, through `jupyter_client` (`AsyncKernelManager`/`AsyncKernelClient`) in `kernels/service.py`. The browser talks to the backend through its own WebSocket protocol, version 1, at `/api/sessions/{id}/channel`: the client sends `execute` (`cell_id`, `code`, `language`), `interrupt` and `restart`; the server sends `status`, `execute_input`, `output`, `clear_output`, `execute_reply` and `error`. Every frame carries `v` and `type`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- The browser never sees the Jupyter messaging protocol; the backend can validate language, cap streams (1 MB per cell) and replace a stale socket.
- The same protocol serves local, DuckDB and Docker kernels.

### Negative
- A custom protocol must be kept in sync between `kernels/protocol.py` and `frontend/src/ws/protocol.ts`.
- Standard Jupyter frontends cannot connect to Notisbook sessions.

### Risks
- Protocol drift between backend and frontend; mitigated by the explicit `v` field and a `bad_message` error.

## Validation
- **Evidence in the code:** `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/kernels/protocol.py`, `backend/src/notisbook/api/sessions.py`, `frontend/src/ws/protocol.ts`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Connection files are kept in `jupyter_runtime_dir()/notisbook/` with mode 0700; `SPARK_HOME`, `PYTHONPATH` and `PYSPARK_*` are removed from the kernel environment.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
