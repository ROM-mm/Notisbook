# ADR-0019: CLI update and uninstall that preserve user data

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Users need to update and remove Notisbook without losing notebooks, lake data or the catalog.

## Decision
`notisbook update [--version]` runs only inside the `uv tool` environment, resolves the target release, refuses downgrades (because of the `catalog.db` schema), downloads `install.sh` and `SHA256SUMS` over HTTPS, verifies `install.sh` and executes it. `notisbook uninstall [--yes]` lists what is removed and kept, asks for confirmation, stops the instance, removes the app-owned Glue container, kernelspecs, `envs/`, MinIO binaries and run files, then runs `uv tool uninstall notisbook`; data is kept.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Updates reuse the verified installer path.
- A reinstall reuses existing data.

### Negative
- Uninstall leaves data behind by design; it must be deleted manually to free space.

### Risks
- Removing folders is guarded: the data folder must carry a marker and cannot be the home folder or an ancestor of it.

## Validation
- **Evidence in the code:** `backend/src/notisbook/maintenance/update.py`, `backend/src/notisbook/maintenance/uninstall.py`, `backend/src/notisbook/maintenance/toolenv.py`, `backend/src/notisbook/__main__.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
`install.sh --uninstall` delegates to `notisbook uninstall --yes` when available.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
