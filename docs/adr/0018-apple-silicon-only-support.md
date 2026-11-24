# ADR-0018: Apple silicon only support

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Every native component (MinIO binary, DuckDB extensions, binary wheels) must be produced and verified per architecture.

## Decision
Notisbook supports only macOS on Apple silicon. `platform_support.is_apple_silicon()` accepts arm64 and x86_64 under Rosetta; the MinIO manifest and DuckDB extensions cover only `darwin-arm64`/`osx_arm64`; the wheel gate checks only `aarch64-apple-darwin`; `install.sh` refuses Intel Macs.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- One architecture to build, verify and test.

### Negative
- Intel Macs cannot run Notisbook; on them the MinIO package is refused and startup fails.

### Risks
- Python under Rosetta relies on arm64 artifacts being usable from the translated process.

## Validation
- **Evidence in the code:** `backend/src/notisbook/platform_support.py`, `backend/src/notisbook/notislake/binary.py`, `backend/src/notisbook/runtimes/duckdb/manifest.py`, `install.sh`, `scripts/build_release.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Native macOS features (folder picker, system fonts) answer `unsupported` outside macOS.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
