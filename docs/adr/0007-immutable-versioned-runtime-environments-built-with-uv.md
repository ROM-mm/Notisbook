# ADR-0007: Immutable, versioned runtime environments built with uv

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Users install several Spark and DuckDB versions side by side, and an install can fail midway.

## Decision

Each install builds a new directory `<home>/envs/spark-<version>-<id8>/` (or `duckdb-<version>-<id>/`) with `uv` (Python 3.12, `uv venv`, `uv pip install`). The new environment is validated with a smoke test before the kernelspec is switched to it; the previous directory is then removed. On failure the new directory is deleted. Subprocesses use argv lists, never a shell.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- A failed install never breaks the working environment.
- Kernelspecs always point to a validated environment.

### Negative

- Reinstalls take extra disk space until the old directory is removed.

### Risks

- Requires `uv` and network access to PyPI during installs.

## Validation

- **Evidence in code:** `backend/src/notisbook/spark/installer.py`, `backend/src/notisbook/runtimes/duckdb/installer.py`
- **How to confirm:** `sed -n 1,10p backend/src/notisbook/spark/installer.py`

## Implementation Notes

Per-environment package management also goes through `uv pip`, restricted to PyPI, with input validated as PEP 508 names and PEP 440 specifiers.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
