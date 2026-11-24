# ADR-0013: AWS Glue runtime in Docker with the catalog through the backend API

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Users want to run AWS Glue 5.0 code locally, but a container must not write the Mac's `catalog.db`.

## Decision
The runtime builds `notisbook/glue:5.0` from the AWS Glue base image pinned by digest and runs one shared, hardened container (`--cap-drop ALL`, `no-new-privileges`, user `hadoop`, owner labels, host network). Each session is a `docker exec` of an ipykernel. The catalog hook uses `http://host.lima.internal:<port>/api/runtime-catalog` and Iceberg uses the backend's REST catalog at `/iceberg`, both with a per-session runtime token; the backend is the only writer of `catalog.db`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- One catalog for local and container runtimes, with no SQLite file shared across the VM boundary.
- Fast session start after the container is up.

### Negative
- Requires Docker and about 15 GiB for the image build.
- Hudi is not registered by this runtime.
- Mounts are fixed at container creation (Recreate to change).

### Risks
- Container escape surface; mitigated by dropped capabilities and refusing sensitive mounts (`$HOME`, `.aws`, `.ssh`, data folder).

## Validation
- **Evidence in the code:** `backend/src/notisbook/runtimes/glue/Dockerfile`, `backend/src/notisbook/runtimes/docker/service.py`, `backend/src/notisbook/runtimes/docker/launch.py`, `backend/src/notisbook/api/runtime_catalog.py`, `backend/src/notisbook/api/iceberg_rest.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
The S3A endpoint on loopback is rewritten to `host.lima.internal` for the container.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
