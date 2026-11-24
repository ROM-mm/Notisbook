# ADR-0012: MinIO binary distributed as a tarball described by a manifest

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
The MinIO binary must be reproducible and verifiable on the user's Mac.

## Decision
`scripts/build_minio.py` builds `minio` and `mc` at fixed tags in a `golang` container for `darwin-arm64` and writes `notislake/minio_manifest.json` (tag, commits, sha256 of tarball and binaries). The installer places the tarball in `${XDG_DATA_HOME:-~/.local/share}/notisbook/notislake`; the backend installs only from there or `NOTISBOOK_MINIO_DIST`, verifying hashes into `<home>/minio/bin/`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- No dependency on third-party MinIO binaries; tampering is detected.

### Negative
- Releases need Docker to build MinIO.
- Only `darwin-arm64` is produced.

### Risks
- A manifest change after build aborts the release, keeping manifest and assets consistent.

## Validation
- **Evidence in the code:** `scripts/build_minio.py`, `backend/src/notisbook/notislake/binary.py`, `backend/src/notisbook/notislake/minio_manifest.json`, `install.sh`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`notisbook --check-notislake` installs the package in a temporary folder and runs `minio --version`.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
