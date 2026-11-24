# ADR-0015: Cell languages per kernel from a single backend table

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Each runtime executes a different set of cell languages.

## Decision
`kernels/service.py` maps kernel kind to languages (local: `python`, `sql`, `duckdb`; DuckDB: `python`, `duckdb`; Docker: `python`, `sql`; non-Python kernels: `python`) and exposes it as `cell_languages` in `/api/kernelspecs`. The UI filters the language menu by it and the backend refuses unsupported languages before sending code.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- One source of truth; UI and backend cannot disagree.

### Negative
- Adding a language needs backend and frontend changes.

### Risks
- Notebooks opened with another kernel may contain cells in unavailable languages; they are refused at execution.

## Validation
- **Evidence in the code:** `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/kernels/languages.py`, `frontend/src/components/notebook/CellHeader.tsx`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
The language is stored in the cell's `metadata.notisbook.language`.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
