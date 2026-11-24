# ADR-0014: DuckDB runtime with its own kernel and Iceberg through the backend REST catalog

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
DuckDB users should query and write lake tables without installing Spark.

## Decision
A separate environment and kernel (`duckdb`) contain `duckdb==2.0.1`, `ipykernel` and pinned extensions verified by sha256 for `osx_arm64`, with autoinstall and autoload off. A silent bootstrap creates S3 and Iceberg secrets with a per-session token and runs `ATTACH 'notislake' (TYPE iceberg, ENDPOINT http://127.0.0.1:<port>/iceberg)`. Credentials never go into `kernel.json`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- DuckDB and Spark share the same Iceberg tables and catalog.
- No Spark dependency in the DuckDB runtime.

### Negative
- DuckDB writes only Iceberg to the notislake.
- Cell languages are limited to `python` and `duckdb`.

### Risks
- DuckDB version differs from the one inside Spark environments (2.0.1 vs 2.0.0).

## Validation
- **Evidence in the code:** `backend/src/notisbook/runtimes/duckdb/installer.py`, `backend/src/notisbook/runtimes/duckdb/hook.py`, `backend/src/notisbook/runtimes/duckdb/extensions.json`, `backend/src/notisbook/api/duckdb_runtime.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Inside Spark kernels, `duckdb` cells use a separate connection without the hook.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
