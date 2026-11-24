# ADR-0021: Apple silicon–only support

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Several bundled components are platform-specific binaries.

## Decision

The supported platform is macOS on Apple silicon (native or under Rosetta). `install.sh` rejects other systems; the backend picks `darwin-arm64` MinIO and `osx_arm64` DuckDB extensions only; release builds target `aarch64-apple-darwin`.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- One platform to build, verify and test.

### Negative

- No Linux, Windows or Intel Mac support.

### Risks

- The server can start on another platform but exits when MinIO fails to start.

## Validation

- **Evidence in code:** `install.sh`, `backend/src/notisbook/platform_support.py`, `backend/src/notisbook/notislake/binary.py`, `backend/src/notisbook/runtimes/duckdb/manifest.py`, `scripts/build_minio.py`
- **How to confirm:** `grep -n 'is_apple_silicon' -r backend/src/notisbook`

## Implementation Notes

macOS tools are used directly: `java_home`, `osascript` (folder picker, fonts), `sysctl`.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
