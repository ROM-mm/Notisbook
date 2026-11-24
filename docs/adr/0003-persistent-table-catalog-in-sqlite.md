# ADR-0003: Persistent table catalog in SQLite (catalog.db)

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Tables created by notebooks must be visible across kernels and sessions, and in the UI without opening a Spark session.

## Decision
Notisbook keeps `<home>/catalog.db` (SQLite, WAL, migrations by `PRAGMA user_version`) with `iceberg_tables`, `iceberg_namespace_properties`, `nb_namespaces`, `nb_tables` and `nb_meta.generation`. The catalog hook reconciles after each cell (`post_run_cell`) and imports changes from other kernels before each cell (`pre_run_cell`) when `generation` changes. The UI reads the catalog through `/api/catalog` without a kernel.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Catalog panel, Catalog info and Table info work with no kernel running.
- One catalog is shared by all runtimes and survives restarts.

### Negative
- Spark runs with `catalogImplementation in-memory`; the hook must reconcile every DDL/write it can observe.
- Changes made outside the hooks (for example by other tools) are not tracked.

### Risks
- Concurrent writers; mitigated by WAL and `BEGIN IMMEDIATE`, and by making the backend the only writer for container and DuckDB runtimes.

## Validation
- **Evidence in the code:** `backend/src/notisbook/catalog/store.py`, `backend/src/notisbook/catalog/registry.py`, `backend/src/notisbook/kernels/catalog_hook.py`, `backend/src/notisbook/api/catalog.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
The database is created or migrated at startup (`__main__.py`).

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
