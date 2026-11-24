# ADR-0002: Hidden kernel modules installed by silent execution

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Cells need a DataFrame renderer and a catalog hook inside every kernel without exposing setup code or outputs to the user.

## Decision
When a kernel is ready, the backend sends a `silent=True, store_history=False` execute that installs the hidden modules `_notisbook_display` (renderer, `echo(df, n=...)`) and `_notisbook_catalog` (catalog hook) or the DuckDB bootstrap. Installation is confirmed through `user_expressions` (3 s budget) and the reply never reaches the WebSocket. Modules are versioned by sha1 and reinstalled only when the version changes.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- No extra packages in the kernel environments; behavior ships with the backend version.
- `echo` replaces `display`, keeping notebooks portable to the Databricks export (which translates it back).

### Negative
- Kernel behavior depends on monkey-patching PySpark (`getOrCreate`, writers, `SparkSession.sql`), sensitive to PySpark internals.

### Risks
- A PySpark change can break the hook silently; the installer smoke test exercises the bundle classes but not every patched path.

## Validation
- **Evidence in the code:** `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/kernels/sql_cell.py`, `backend/src/notisbook/kernels/catalog_hook.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`echo` shows 50 rows by default and up to 1000 (`MAX_ROWS`). `display` is not defined in cells.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
