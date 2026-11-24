# ADR-0004: App-exclusive kernelspec directory

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Kernels for Spark, DuckDB and Docker runtimes are created by the app. Other Jupyter kernels may exist on the user's machine.

## Decision

`KernelSpecManager` is configured with `kernel_dirs=[<home>/kernels]` and `ensure_native_kernel=False`. Only app-managed kernelspecs are listed or launched; unmanaged names are refused. Legacy specs found in the global Jupyter folder are migrated.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Kernel lists show only environments the app knows how to configure (catalog, storage, languages).

### Negative

- Kernels installed by the user outside Notisbook cannot be used.

### Risks

- None identified beyond the restriction above.

## Validation

- **Evidence in code:** `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/spark/kernelspec.py`
- **How to confirm:** `grep -n 'kernel_dirs\|ensure_native_kernel' backend/src/notisbook/kernels/service.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
