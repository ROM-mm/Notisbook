# ADR-0020: Orderly shutdown and version handover via the instance record

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Only one backend may own a data folder, and installing a new version must replace a running old one.

## Decision
At startup the backend writes `<home>/run/backend.json` (0600) with `{pid, port, version, token}`. A new process removes stale records, asks a running instance of a different version to stop through `POST /api/lifecycle/shutdown` with that token and waits up to 60 s; the same version running makes startup fail. `--stop-running` stops any registered instance. Shutdown stops installers, kernels and containers and removes the record only if it belongs to the process.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Updates replace the running app without manual steps.
- No two backends compete for MinIO and the catalog.

### Negative
- Running the same version twice is refused; development uses `start.sh --replace`.

### Risks
- A frozen process can block startup; a pid alive with a silent port for more than 10 s is reported as an error.

## Validation
- **Evidence in the code:** `backend/src/notisbook/api/lifecycle.py`, `backend/src/notisbook/__main__.py`, `start.sh`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
The shutdown route accepts only loopback clients.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
