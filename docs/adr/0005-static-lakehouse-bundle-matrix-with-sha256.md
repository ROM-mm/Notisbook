# ADR-0005: Static lakehouse bundle matrix with sha256

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Delta, Iceberg, Hudi and S3A jars must match each Spark line and be reproducible offline-verifiable downloads.

## Decision
`spark/bundles.py` defines a static matrix (revision 4) for Spark 3.5.0–3.5.2, 3.5.3+ and 4.1, pinning Delta, Iceberg, Hudi, `hadoop-aws`, the AWS SDK bundle, wildfly-openssl and `sqlite-jdbc`, each with a sha256. Jars are downloaded to `.part`, verified and then renamed; a mismatch fails the install. A Spark version without a bundle installs Spark only and its kernel is refused (`spark_env_outdated`).

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Known-good combinations; tampered or corrupted jars are rejected.
- The kernelspec records bundle key and revision, so outdated environments are detected.

### Negative
- Every new Spark line requires a code change and a release.
- The version list can suggest versions without a bundle (observed: `4.3.0` in the static fallback).

### Risks
- Spark 3.5 keeps `hadoop-aws` 3.3.4 with AWS SDK v1; an SDK upgrade needs a new bundle revision.

## Validation
- **Evidence in the code:** `backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/spark/installer.py`, `backend/src/notisbook/spark/catalog.py`, `backend/src/notisbook/spark/kernelspec.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`NOTISBOOK_MAVEN_URL` replaces Maven Central as the jar source.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
