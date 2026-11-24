# ADR-0008: Pinned lakehouse bundle matrix with sha256 and a content-addressed jar cache

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Delta Lake, Iceberg and Hudi jars must match the Spark and Scala versions of each environment.

## Decision

`spark/bundles.py` defines a static `MATRIX` per Spark line (`3.5.0-3.5.2`, `3.5`, `4.1`) with each jar pinned by sha256 and a `revision` number; bumping it marks existing environments as outdated. Jars are downloaded from Maven Central into a shared cache `<home>/jars/<sha256>/<file>`. The cache keeps no index: usage is derived from the `spark-defaults.conf` files on disk.

**Rationale:** The code states that the cache has no index to avoid divergence after a crash, given SDK v2 jars of 558–686 MB. The pinning itself: Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Reproducible environments with integrity checks.
- Large jars are downloaded once and shared.

### Negative

- Spark lines without an entry (for example 4.0, 4.2, 4.3) open sessions without the table formats.

### Risks

- New Spark versions need a manual matrix update.

## Validation

- **Evidence in code:** `backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/spark/jar_cache.py`
- **How to confirm:** `grep -n 'MATRIX\|revision' backend/src/notisbook/spark/bundles.py`

## Implementation Notes

Current entries: Delta 3.2.0/3.3.3/4.1.0, Iceberg 1.10.1/1.12.0, Hudi 1.2.1. Before each local kernel start, `spark-defaults.conf` is re-rendered from the matrix; missing jars return 409.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
