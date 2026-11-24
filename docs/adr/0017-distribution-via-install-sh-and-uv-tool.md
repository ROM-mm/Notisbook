# ADR-0017: Distribution via install.sh and uv tool with a binary-wheel gate

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
macOS users must install the backend, the embedded frontend and the MinIO package with integrity checks and without compiling anything.

## Decision
Each GitHub release publishes the wheel, `constraints-<v>.txt` exported from `uv.lock`, the MinIO tarball for `darwin-arm64`, `SHA256SUMS` and `install.sh`. The build aborts if any dependency lacks a binary wheel for `aarch64-apple-darwin`. `install.sh` verifies sha256 before changing anything, stops the running instance, runs `uv tool install --force --managed-python --no-build -c constraints` on Python 3.12, places the MinIO tarball and runs `notisbook --check-notislake`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Nothing compiles on the user's Mac; versions are pinned by the lock.
- Re-running the installer updates.

### Negative
- Depends on `uv` (installs 0.10.8 when missing; minimum 0.8.4).

### Risks
- Another `notisbook` on the `PATH` can shadow the installed one; the installer and `release.sh --local-install` check the `uv tool` bin directory.

## Validation
- **Evidence in the code:** `install.sh`, `scripts/release.sh`, `scripts/build_release.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`NOTISBOOK_INSTALL_FROM=<dir>` installs from local assets; `release.sh --local-install` uses it to install a version before publishing.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
