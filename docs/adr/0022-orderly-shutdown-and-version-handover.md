# ADR-0022: Orderly shutdown and version handover

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Starting a new version while an older one is running would leave two apps fighting over the same data.

## Decision

A running instance writes `<home>/run/backend.json` (pid, port, version, shutdown token; 0600). On start, a live instance of a different version is asked to stop through `POST /api/lifecycle/shutdown` with its own token, and the new one waits up to 60 s; the same version is refused. Shutdown stops installers, kernels and owned containers, then MinIO.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Updates do not leave orphan servers or kernels.

### Negative

- A hung old instance blocks the new one until the wait expires.

### Risks

- The shutdown route accepts only loopback clients with the separate token.

## Validation

- **Evidence in code:** `backend/src/notisbook/api/lifecycle.py`, `backend/src/notisbook/__main__.py`, `backend/src/notisbook/app.py`
- **How to confirm:** `grep -n 'EXIT_WAIT_S\|backend.json' backend/src/notisbook/api/lifecycle.py`

## Implementation Notes

`notisbook --stop-running` stops the registered instance of any version.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
