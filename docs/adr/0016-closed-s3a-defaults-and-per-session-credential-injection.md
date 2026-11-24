# ADR-0016: Closed S3A defaults on disk and per-session credential injection

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Spark environments need object-store credentials, but files on disk and process listings can leak them.

## Decision

`spark-defaults.conf` carries closed S3A options (dead endpoint `http://127.0.0.1:1`, anonymous provider). Real per-bucket options (`fs.s3a.bucket.notislake.*`) are injected into each session by the silent hook. Credentials never go into argv, `kernel.json` or logs; `repr` masks them. Session opening fails closed when storage is unavailable or misconfigured.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- No secret is persisted in environment files.
- A misconfigured store does not silently write elsewhere.

### Negative

- A kernel started outside the app has no storage access.

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/notislake/sparkconf.py`, `backend/src/notisbook/kernels/service.py`
- **How to confirm:** `sed -n 1,10p backend/src/notisbook/notislake/sparkconf.py`

## Implementation Notes

For Docker kernels the loopback endpoint is rewritten to `host.lima.internal`.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
