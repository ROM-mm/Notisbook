# ADR-0006: Cell languages per kernel, enforced by the backend

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

A notebook can mix Python, Spark SQL and DuckDB cells, but not every runtime supports every language.

## Decision

The backend holds the table of allowed languages per runtime kind: local Spark → `python`, `sql`, `duckdb`; DuckDB → `python`, `duckdb`; Docker (Glue) → `python`, `sql`; non-Python kernels → `python` only. A disallowed language is refused before any code is sent to the kernel.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- One source of truth for the UI selector and execution validation.

### Negative

- Adding a language requires backend and frontend changes.

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/kernels/languages.py`, `frontend/src/api/types.ts`
- **How to confirm:** `grep -n 'python\|duckdb' backend/src/notisbook/kernels/languages.py`

## Implementation Notes

Labels: `python` = Python, `sql` = Spark SQL, `duckdb` = DuckDB.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
