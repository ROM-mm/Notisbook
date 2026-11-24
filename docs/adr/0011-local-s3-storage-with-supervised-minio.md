# ADR-0011: Local S3 storage with a supervised MinIO (notislake)

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Lakehouse formats should run against S3 semantics locally, with layers and without a cloud account.

## Decision
The backend starts and supervises a MinIO (`flock` per data folder, two loopback ports, health check, restart with backoff) serving bucket `notislake` with `bronze/`, `silver/` and `gold/`. The schema decides the layer and managed tables live at `s3a://notislake/<layer>/<table>`; a wrong destination fails before writing. S3A uses per-bucket keys and the credential is applied after `getOrCreate`. A valid `notislake-connection.json` switches to a manual S3 endpoint; in automatic mode a session fails closed without MinIO.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Same paths and S3A code as a cloud lake; layers are enforced.
- Credentials never appear in argv or kernelspecs.

### Negative
- MinIO is mandatory in automatic mode: the app does not start without it.
- The local credential is returned to the UI on request (Copy credentials).

### Risks
- MinIO binary supply; mitigated by building it ourselves and pinning sha256 in a manifest.

## Validation
- **Evidence in the code:** `backend/src/notisbook/notislake/supervisor.py`, `backend/src/notisbook/notislake/bootstrap.py`, `backend/src/notisbook/notislake/sparkconf.py`, `backend/src/notisbook/notislake/locations.py`, `backend/src/notisbook/notislake/objectstore.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`bronze`, `silver` and `gold` cannot be dropped; `landing` is a free zone, not a layer.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
