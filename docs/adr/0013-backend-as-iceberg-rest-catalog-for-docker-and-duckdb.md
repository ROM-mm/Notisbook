# ADR-0013: Backend as an Iceberg REST catalog for Docker and DuckDB kernels

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Kernels inside Docker and the DuckDB runtime cannot or should not open `catalog.db` directly.

## Decision

The backend implements an Iceberg REST catalog under `/iceberg/v1/...`, using `pyiceberg` as a domain library and compare-and-swap on `metadata_location` in SQLite. Glue kernels reach it at `http://host.lima.internal:<port>/iceberg`; DuckDB attaches it at `http://127.0.0.1:<port>/iceberg`. Non-Iceberg registry operations from Docker go through `/api/runtime-catalog`. These routes accept only per-session runtime tokens.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- The container never sees `catalog.db` or the user's AWS files.
- All runtimes share one catalog.

### Negative

- The backend must keep a REST catalog implementation compatible with Spark and DuckDB clients.

### Risks

- The REST implementation is large and was only partially analyzed for this record.

## Validation

- **Evidence in code:** `backend/src/notisbook/api/iceberg_rest.py`, `backend/src/notisbook/api/runtime_catalog.py`, `backend/src/notisbook/runtimes/docker/incontainer.py`, `backend/src/notisbook/runtimes/duckdb/hook.py`
- **How to confirm:** `grep -n 'iceberg' backend/src/notisbook/runtimes/duckdb/hook.py`

## Implementation Notes

`/v1/config` forces `io-impl` to `HadoopFileIO`.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
