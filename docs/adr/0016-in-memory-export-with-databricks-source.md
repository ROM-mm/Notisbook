# ADR-0016: Stateless in-memory export with Databricks source translation

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Users export notebooks to other platforms without touching the files on disk.

## Decision
`POST /api/export/{py|ipynb|html}` transforms the notebook sent by the frontend (limit 50 MB), never reading or writing disk. `.py` is Databricks *notebook source*: markdown becomes `# MAGIC %md`, SQL cells become `spark.sql(...)` per statement, `echo(df, n=...)` becomes `display(df)` and DuckDB cells become commented warnings. `.html` is a self-contained report without JavaScript.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Exports reflect unsaved edits; no files are created as a side effect.

### Negative
- DuckDB cells have no Databricks equivalent.
- `.dbc` is not supported.

### Risks
- Translation heuristics (statement splitting, `echo` rewriting) can miss unusual code; strings and comments are skipped.

## Validation
- **Evidence in the code:** `backend/src/notisbook/api/export.py`, `backend/src/notisbook/export/py_source.py`, `backend/src/notisbook/export/html_report.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Responses carry `nosniff`, `no-store` and a sanitized `Content-Disposition`.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
