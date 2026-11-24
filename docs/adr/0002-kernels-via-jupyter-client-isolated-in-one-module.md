# ADR-0002: Kernels managed through jupyter_client, isolated in one module

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Notebook cells run in Jupyter kernels (ipykernel) for local Spark, DuckDB and Docker runtimes. The backend needs to start, interrupt, restart and talk to these kernels.

## Decision

Kernels are managed with `jupyter_client` (`AsyncKernelManager`, one per session). `kernels/service.py` is the only module that imports `jupyter_client`. Connection files live under the Jupyter runtime directory in a `notisbook/` subfolder (mode 0700); orphans from a previous run on the same port are removed at startup.

**Rationale:** The module docstring states that isolating the import keeps the backend swappable for `jupyter_server`.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- The kernel layer can be replaced without touching the API routers.
- Uses the standard Jupyter wire protocol, so any ipykernel-based environment works.

### Negative

- The app re-implements session management that `jupyter_server` would otherwise provide.

### Risks

- Changes in `jupyter_client` behavior surface in a single module, which concentrates maintenance.

## Validation

- **Evidence in code:** `backend/src/notisbook/kernels/service.py`
- **How to confirm:** `grep -rn 'import jupyter_client\|from jupyter_client' backend/src/notisbook`

## Implementation Notes

Kernel environments are scrubbed of `SPARK_HOME`, `PYTHONPATH`, `PYSPARK_*` and `SPARK_CONF_DIR` before launch.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
