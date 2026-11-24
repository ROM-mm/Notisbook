# ADR-0009: S3A jars selected by the Hadoop version bundled in pyspark

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

S3A support needs `hadoop-aws` and an AWS SDK matching the Hadoop libraries inside each pyspark wheel.

## Decision

The installer detects the Hadoop version from the `hadoop-client-api-*.jar` inside the installed pyspark and picks the S3A jars from `S3A_BY_HADOOP` (3.3.4, 3.4.1, 3.4.2, 3.5.0). An unknown Hadoop version fails the install.

**Rationale:** The code states that mixing versions breaks `S3AFileSystem`.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- S3A works for every supported pyspark without manual configuration.

### Negative

- A new pyspark with an unmapped Hadoop version cannot be installed until the table is updated.

### Risks

- Failing closed prevents a broken environment from being published.

## Validation

- **Evidence in code:** `backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/spark/installer.py`
- **How to confirm:** `grep -n 'S3A_BY_HADOOP' backend/src/notisbook/spark/bundles.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
