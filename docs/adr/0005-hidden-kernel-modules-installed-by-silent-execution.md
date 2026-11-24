# ADR-0005: Hidden kernel modules installed by silent execution

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

SQL/DuckDB cells, rich table rendering and catalog synchronization need code running inside each kernel.

## Decision

After a kernel is ready, the backend sends one `execute` with `silent=True`, `store_history=False` that installs two hidden modules: `_notisbook_display` (renders SQL/DuckDB results as HTML tables with an ASCII fallback) and `_notisbook_catalog` (patches Spark session, writers and `createTable` to reconcile with the app catalog and enforce destination rules). The DuckDB runtime uses the same mechanism for its bootstrap (secrets and `ATTACH`).

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- The user namespace is not polluted and nothing appears in cell history.
- Credentials are injected at runtime instead of being written to kernel files.

### Negative

- Behavior depends on monkey-patching Spark APIs, which is sensitive to Spark version changes.

### Risks

- A failed install is detected through `user_expressions`; the hook is large (over 2,000 lines) and only its docstring was analyzed for this record.

## Validation

- **Evidence in code:** `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/kernels/sql_cell.py`, `backend/src/notisbook/kernels/catalog_hook.py`, `backend/src/notisbook/runtimes/duckdb/hook.py`
- **How to confirm:** `grep -n 'silent=True' backend/src/notisbook/kernels/service.py`

## Implementation Notes

SQL results are capped (1,000 rows fetched, 50 displayed, 500 characters per cell). Queries are passed as JSON literals, never spliced into code.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
