# ADR-0007: Kernel JDK chosen by Spark line

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Spark 3.x and 4.x need different Java versions and users may have several JDKs.

## Decision
Spark 3.x uses JDK 17; other lines use 21, or 17 when 21 is missing (minimum 17). The JDK is searched in `JAVA_HOME`, `/usr/libexec/java_home -v <major>` and Homebrew `openjdk@<major>`, and written as `JAVA_HOME` in the kernelspec.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Each kernel runs with a compatible JDK regardless of the shell's `JAVA_HOME`.

### Negative
- The JDK is not installed by Notisbook; the user must provide it.

### Risks
- A JDK removed after install breaks the kernel until the runtime is reinstalled.

## Validation
- **Evidence in the code:** `backend/src/notisbook/spark/prereqs.py`, `backend/src/notisbook/spark/kernelspec.py`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Prerequisites are reported by `GET /api/system/prereqs`.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
