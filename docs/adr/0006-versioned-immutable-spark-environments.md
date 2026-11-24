# ADR-0006: Versioned, immutable Spark environments

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Installing or upgrading a Spark runtime must not break a working kernel.

## Decision
Each Spark version is installed into a new `<home>/envs/spark-<version>-<id>/` environment (Python 3.12 via `uv`, `pyspark`, `ipykernel`, `duckdb`, bundle jars). Phases: prereqs → python → venv → install → bundle → validate → kernelspec → cleanup. The kernelspec is switched only after validation (version checks and a smoke test with a throwaway `catalog.db`); any failure deletes the new environment.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- A failed install keeps the previous environment and kernel.
- Environments are isolated from the user's Python.

### Negative
- Disk usage grows with each installed version.
- Library changes are blocked while a session uses the environment.

### Risks
- Leftover environments after crashes; uninstall removes `envs/`.

## Validation
- **Evidence in the code:** `backend/src/notisbook/spark/installer.py`, `backend/src/notisbook/spark/kernelspec.py`, `backend/src/notisbook/spark/packages.py`, `backend/src/notisbook/api/spark.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Libraries are managed with `uv pip` and a filtered environment; base libraries are protected.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
