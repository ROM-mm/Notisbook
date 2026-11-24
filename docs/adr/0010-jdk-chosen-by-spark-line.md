# ADR-0010: JDK chosen by Spark line and discovered on macOS

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Spark 3.x and 4.x support different Java versions.

## Decision

Spark 3.x requires JDK 17; Spark 4.x accepts 21, then 17. The JDK is resolved from `$JAVA_HOME` if its major version is accepted, then `/usr/libexec/java_home -v <major>`, then Homebrew `openjdk@<major>`. No JDK is installed by the app; a missing one is an install error naming the required majors.

**Rationale:** Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Uses JDKs the user already manages.

### Negative

- The user must install a JDK separately.

### Risks

- None identified.

## Validation

- **Evidence in code:** `backend/src/notisbook/spark/prereqs.py`
- **How to confirm:** `grep -n 'java_home\|openjdk' backend/src/notisbook/spark/prereqs.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
