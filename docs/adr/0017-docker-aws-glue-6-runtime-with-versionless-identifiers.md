# ADR-0017: Docker AWS Glue 6.0 runtime with version-less identifiers

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Users want to run notebooks against an AWS Glue–compatible Spark locally.

## Decision

The Docker runtime catalog has one entry: key `glue`, label "AWS Glue 6.0", image `notisbook/glue:6.0` built locally from `public.ecr.aws/glue/aws-glue-libs:6.0` pinned by digest. The container (`notisbook-glue`) and kernel (`notisbook-docker-glue`) names carry no version. The container is persistent and owned by the app (labels), runs as `hadoop` with `--cap-drop ALL`, `no-new-privileges`, `--init` and host networking, and mounts only allowed paths inside `$HOME`. Kernels start through `docker exec`.

**Rationale:** The code states that only `$HOME` is mounted because Colima shares only `$HOME`, and that `--init` avoids zombie JVM processes. The version-less names: Historical rationale not recoverable from the code.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Upgrading the Glue version does not orphan containers or kernels by name.
- The container never sees `~/.aws`, SSH keys or `catalog.db`.

### Negative

- The image build needs at least 15 GiB free and can take up to an hour.

### Risks

- Assumes a Colima-style Docker host (`host.lima.internal`). Same-name containers without app labels are treated as foreign and never altered.

## Validation

- **Evidence in code:** `backend/src/notisbook/runtimes/docker/catalog.py`, `backend/src/notisbook/runtimes/docker/service.py`, `backend/src/notisbook/runtimes/glue/Dockerfile`, `backend/src/notisbook/runtimes/docker/launch.py`
- **How to confirm:** `grep -n 'glue' backend/src/notisbook/runtimes/docker/catalog.py; head -8 backend/src/notisbook/runtimes/glue/Dockerfile`

## Implementation Notes

A Dockerfile comment states that Glue 6.0 ships Spark 4.1, Scala 2.13, Python 3.13 and Java 17 (not verified against the image). Validation runs offline with an in-memory catalog; the AWS Glue Data Catalog is not used.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
