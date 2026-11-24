# ADR-0018: DuckDB runtime with its own kernel and offline extensions

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Users want lightweight SQL on lakehouse data without starting a JVM.

## Decision

DuckDB runs in its own immutable environment and kernel (`duckdb-<maj>-<min>-<patch>`). Extensions (httpfs, iceberg, avro, excel, sqlite_scanner, postgres_scanner, spatial) are downloaded from `extensions.duckdb.org` with a double sha256 check and loaded offline. At kernel start, temporary secrets for S3 and the Iceberg REST catalog are created and `notislake` is attached as an Iceberg catalog. The manifest lists versions 2.0.1 and 1.5.6, for `osx_arm64` only.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Fast startup and low memory compared with Spark.
- No credentials in `kernel.json`.

### Negative

- Only Iceberg tables are reachable through the attached catalog.

### Risks

- Spark environments pin `duckdb==2.0.0` for DuckDB cells, which differs from the runtime manifest.

## Validation

- **Evidence in code:** `backend/src/notisbook/runtimes/duckdb/installer.py`, `backend/src/notisbook/runtimes/duckdb/extensions.json`, `backend/src/notisbook/runtimes/duckdb/hook.py`, `backend/src/notisbook/runtimes/duckdb/kernelspec.py`
- **How to confirm:** `cat backend/src/notisbook/runtimes/duckdb/extensions.json`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
