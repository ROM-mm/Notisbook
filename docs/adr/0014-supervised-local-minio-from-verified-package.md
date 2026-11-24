# ADR-0014: Supervised local MinIO (notislake) from a verified, pre-placed package

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Lakehouse tables need S3-compatible object storage on the user's machine.

## Decision

The app supervises a local MinIO server called notislake. The binary comes from a package placed by `install.sh` (or `$NOTISBOOK_MINIO_DIST`), is verified against `minio_manifest.json` (sha256 of tarball and binaries) and is never downloaded by the backend. One supervisor per data folder (`flock`), two dynamic loopback ports, restart with backoff (1–16 s), and a `failed` state on crash loops. Credentials are random, stored in a 0600 file and passed only through the child environment.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Works offline after installation.
- Integrity is checked before execution.

### Negative

- MinIO adds a resident process and its own AGPLv3 license in the distributed tarball.

### Risks

- If MinIO is not running, new sessions are refused (503 `notislake_unavailable`).

## Validation

- **Evidence in code:** `backend/src/notisbook/notislake/binary.py`, `backend/src/notisbook/notislake/supervisor.py`, `backend/src/notisbook/notislake/credentials.py`, `backend/src/notisbook/notislake/minio_manifest.json`, `scripts/build_minio.py`
- **How to confirm:** `sed -n 1,12p backend/src/notisbook/notislake/supervisor.py`

## Implementation Notes

A manual S3-compatible connection can replace the local MinIO (`notislake-connection.json`).

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
