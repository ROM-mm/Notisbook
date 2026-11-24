# ADR-0026: In-memory job registry with replayable progress events

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Installs of Spark, DuckDB and Docker runtimes take minutes and must report progress to the UI.

## Decision

Long operations run as jobs in an in-memory `JobRegistry` with an event log. `WS /api/jobs/{job_id}/events` replays the accumulated log on every connection and ends with `{phase: "done"}` and close code 1000.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- A reloaded page can resume the progress view.

### Negative

- Job history is lost when the app restarts.

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/jobs.py`, `backend/src/notisbook/api/jobs.py`, `frontend/src/ws/jobs.ts`
- **How to confirm:** `sed -n 1,15p backend/src/notisbook/jobs.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
