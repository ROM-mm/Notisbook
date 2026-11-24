# ADR-0019: Single data root and a default notebooks folder with seeded samples

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

The app stores environments, catalog, storage, credentials and notebooks, and must find them again after updates.

## Decision

Everything lives under one data root, `$NOTISBOOK_HOME` or `~/.notisbook` (`catalog.db`, `envs/`, `kernels/`, `jars/`, `minio/`, `run/`, `preferences.json`, `notebooks/`, warehouses). The default notebooks root is `<home>/notebooks`. On first run the app adopts an existing `~/notebooks` with notebooks, or seeds sample notebooks (Spark, Glue and DuckDB) without overwriting files.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Uninstall and update can reason about one folder.
- New users get working examples.

### Negative

- The notebooks root cannot be `/`, the home folder or the data folder itself (except `notebooks/`).

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/config.py`, `backend/src/notisbook/onboarding.py`, `backend/src/notisbook/preferences.py`, `backend/src/notisbook/samples/`
- **How to confirm:** `grep -n 'NOTISBOOK_HOME' backend/src/notisbook/config.py`

## Implementation Notes

`--root` overrides the saved preference and locks the folder selection in the UI.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
