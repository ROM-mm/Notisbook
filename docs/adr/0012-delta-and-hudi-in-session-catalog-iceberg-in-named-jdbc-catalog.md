# ADR-0012: Delta and Hudi in the session catalog, Iceberg in a named JDBC catalog

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Local Spark sessions must support Delta Lake, Iceberg and Hudi at the same time.

## Decision

`spark_catalog` is `DeltaCatalog` and also registers Hudi tables (Hudi appears as a display-only node in the UI). Iceberg lives in a separate catalog named `iceberg` (`type=jdbc` over `catalog.db`, warehouse `s3a://notislake`, `HadoopFileIO`, `gc.enabled=false`). The Spark session catalog is in-memory (no Hive metastore).

**Rationale:** The code states that `SparkSessionCatalog` and `DeltaCatalog` cannot share the session catalog slot; that an embedded Hive metastore would create files in the notebook's working directory; that GC is disabled because the bucket is shared; and that S3FileIO would need its own SDK wiring.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- All three formats work in one session.

### Negative

- Iceberg tables need the `iceberg.` prefix.

### Risks

- With Iceberg GC disabled, unreferenced files are not cleaned automatically.

## Validation

- **Evidence in code:** `backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/catalog/registry.py`
- **How to confirm:** `grep -n 'spark_catalog\|catalog.iceberg' backend/src/notisbook/spark/bundles.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
