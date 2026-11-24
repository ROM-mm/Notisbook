# ADR-0025: Stateless in-memory notebook export

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Users export notebooks to other platforms and to shareable reports.

## Decision

`POST /api/export/{fmt}` (`py`, `ipynb`, `html`) receives the notebook in the request body and returns the file without reading or writing disk. `py` is Databricks notebook source (Spark SQL cells become `spark.sql`; DuckDB cells are kept as comments with a warning). `html` is a self-contained report without JavaScript. Bodies over 50 MB return 413.

**Rationale:** The code describes the export as stateless by design.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- No temporary files or cleanup.
- Unsaved changes can be exported.

### Negative

- Large notebooks travel twice over the local connection.

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/api/export.py`, `backend/src/notisbook/export/py_source.py`, `backend/src/notisbook/export/html_report.py`
- **How to confirm:** `sed -n 1,10p backend/src/notisbook/api/export.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
