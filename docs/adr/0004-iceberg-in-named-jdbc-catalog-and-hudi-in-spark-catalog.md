# ADR-0004: Iceberg in a named JDBC catalog; Delta, Parquet and Hudi in spark_catalog

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Delta, Parquet, Hudi and Iceberg tables must coexist in one Spark session and in one catalog view.

## Decision
`spark_catalog` is the `DeltaCatalog` and holds Delta, Parquet and Hudi tables. Iceberg lives in a named catalog `iceberg` (`SparkCatalog`, type `jdbc` over `catalog.db`, warehouse `s3a://notislake`, `gc.enabled=false`, `HadoopFileIO`). `hudi` is only a display node in the UI; a named `hudi.*` catalog is not used.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Iceberg metadata is stored in the same SQLite file, readable by the backend's Iceberg REST endpoint.
- Each format uses its native catalog integration.

### Negative
- Users must address Iceberg tables as `iceberg.<schema>.<table>`.
- Hudi appears under a display group that is not a real Spark catalog.

### Risks
- Iceberg JDBC schema changes between Iceberg versions; the tables mirror the Iceberg 1.10.1 JDBC schema V1.

## Validation
- **Evidence in the code:** `backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/catalog/registry.py`, `backend/src/notisbook/catalog/iceberg_jdbc.py`, `backend/src/notisbook/catalog/catalog_info.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Dropping an Iceberg table removes only the registry entry unless `PURGE` is used.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
