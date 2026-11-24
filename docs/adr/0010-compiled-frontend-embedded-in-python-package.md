# ADR-0010: Compiled frontend embedded in the Python package

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Users must install one artifact and not need Node.js.

## Decision
`scripts/build_release.py` builds the React frontend and copies it to `backend/src/notisbook/_frontend/`, which hatchling ships inside the wheel and sdist; the build checks that `notisbook/_frontend/index.html` is present. In development `NOTISBOOK_FRONTEND_DIST` or `frontend/dist` take precedence.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- A single wheel contains backend and UI; the same version runs both.

### Negative
- Every UI change requires a new wheel.

### Risks
- A stale `_frontend` in development; mitigated by `frontend/dist` precedence and `start.sh` rebuilds.

## Validation
- **Evidence in the code:** `scripts/build_release.py`, `backend/pyproject.toml`, `backend/src/notisbook/config.py`, `backend/src/notisbook/static.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
The SPA is served with a strict CSP.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
