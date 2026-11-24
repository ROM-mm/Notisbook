# ADR-0020: Distribution as a uv tool, with the compiled frontend embedded in the wheel

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

End users need a one-command install on macOS without managing Python themselves.

## Decision

Releases publish a wheel, a constraints file, the MinIO tarball, `SHA256SUMS` and `install.sh` on GitHub. `install.sh` checks the platform, installs `uv` if missing, verifies every download against `SHA256SUMS` and runs `uv tool install --python 3.12 --no-build`. The React build is copied into `notisbook/_frontend` (gitignored) and forced into the wheel by hatch `artifacts`. `notisbook update` re-runs a checksum-verified `install.sh`; `notisbook uninstall` removes the tool but keeps user data.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- One artifact contains backend and UI.
- Integrity checks on every installed file.

### Negative

- No PyPI publication; installation depends on GitHub releases.

### Risks

- Downgrades are refused by the updater.

## Validation

- **Evidence in code:** `install.sh`, `scripts/release.sh`, `scripts/build_release.py`, `backend/pyproject.toml`, `backend/src/notisbook/maintenance/update.py`, `backend/src/notisbook/maintenance/uninstall.py`
- **How to confirm:** `grep -n 'uv tool install' install.sh; grep -n 'artifacts' backend/pyproject.toml`

## Implementation Notes

Uninstall keeps `minio/data`, credentials, `catalog.db`, warehouses, preferences and notebooks.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
