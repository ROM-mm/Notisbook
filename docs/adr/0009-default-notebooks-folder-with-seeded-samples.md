# ADR-0009: Default notebooks folder with seeded samples

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
A first-time user needs working notebooks for each runtime.

## Decision
The notebooks root is `--root` (locks the UI), else the saved preference, else `<home>/notebooks`. On the first run (no `preferences.json`), an existing `~/notebooks` with notebooks is adopted when `NOTISBOOK_HOME` is not set; otherwise the bundled samples `delta`, `iceberg`, `hudi`, `duckdb` and `glue` are copied without overwriting and `samples_seeded` is recorded so deleted samples are not recreated.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Examples on the Home screen show the runtime each one needs and deep-link to its setup.

### Negative
- Samples are copies; later releases do not update them.

### Risks
- Failures in onboarding are only warnings and do not block startup.

## Validation
- **Evidence in the code:** `backend/src/notisbook/onboarding.py`, `backend/src/notisbook/preferences.py`, `backend/src/notisbook/api/samples.py`, `backend/src/notisbook/samples/`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Spark samples write EXTERNAL tables to the `bronze` layer so they can be re-run.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
