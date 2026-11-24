# ADR-0008: Single data root in NOTISBOOK_HOME

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Environments, catalog, lake data, credentials and preferences must live in one predictable place that survives reinstalls.

## Decision
All state lives under `NOTISBOOK_HOME` (default `~/.notisbook`): `envs/`, `catalog.db`, `notebooks/`, `warehouse/`, `spark-warehouse/`, `minio/`, `notislake-connection.json`, `preferences.json` and `run/backend.json`. Sensitive files are written with mode 0600.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Uninstall can remove software and keep data; a reinstall picks it up again.
- A separate `NOTISBOOK_HOME` isolates test installations.

### Negative
- One backend and one MinIO per data folder (enforced by locks and the instance record).

### Risks
- Deleting the folder deletes lake data and catalog together.

## Validation
- **Evidence in the code:** `backend/src/notisbook/config.py`, `backend/src/notisbook/preferences.py`, `backend/src/notisbook/maintenance/uninstall.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
The software package itself lives in the `uv tool` environment, outside the data folder.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
