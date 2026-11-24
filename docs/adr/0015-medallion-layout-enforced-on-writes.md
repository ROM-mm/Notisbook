# ADR-0015: Medallion layout enforced on writes

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Data written from notebooks should land in predictable locations.

## Decision

The bucket `notislake` has the prefixes `landing/`, `bronze/`, `silver/` and `gold/`. The catalog hook enforces destination rules before writes, and the `bronze`, `silver` and `gold` schemas cannot be dropped.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Consistent storage layout across runtimes.

### Negative

- Writes outside the layout are refused.

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/notislake/locations.py`, `backend/src/notisbook/kernels/catalog_hook.py`, `backend/src/notisbook/catalog/schemas.py`
- **How to confirm:** `sed -n 1,25p backend/src/notisbook/notislake/locations.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
