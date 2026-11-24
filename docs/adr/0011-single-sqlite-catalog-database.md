# ADR-0011: Single SQLite database as the persistent table catalog

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Tables created in notebooks must survive kernel restarts and be visible from every runtime.

## Decision

One SQLite file, `<home>/catalog.db` (WAL, `BEGIN IMMEDIATE`, busy timeout 5 s, migrations by `PRAGMA user_version`), holds two catalogs: the app's own registry (`nb_namespaces`, `nb_tables`, `nb_meta.generation`) for `spark_catalog` tables, and the Iceberg JdbcCatalog tables (`iceberg_tables`, `iceberg_namespace_properties`). The backend is the only component that creates or alters the schema, at startup.

**Rationale:** The code states that the backend creates the Iceberg tables itself (`jdbc.init-catalog-tables=false`) because the catalog's own initialization pins a read snapshot and breaks commits.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- No external metastore service.
- Every write bumps `generation`, so open sessions reconcile.

### Negative

- Concurrent writers are serialized by SQLite locking.

### Risks

- Downgrading the app is refused because `catalog.db` may have a newer schema.

## Validation

- **Evidence in code:** `backend/src/notisbook/catalog/store.py`, `backend/src/notisbook/catalog/registry.py`, `backend/src/notisbook/catalog/iceberg_jdbc.py`, `backend/src/notisbook/spark/bundles.py`
- **How to confirm:** `grep -n 'user_version\|CREATE TABLE' backend/src/notisbook/catalog/store.py`

## Implementation Notes

Layers `bronze`, `silver` and `gold` are seeded in both catalogs and cannot be dropped.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
