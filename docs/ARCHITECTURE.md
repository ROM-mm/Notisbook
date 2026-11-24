# Notisbook Architecture

This document describes the architecture observed in the source code of Notisbook `0.13.1` (`backend/pyproject.toml`). Every statement cites the files it comes from. Runtime behavior that the code cannot prove (performance, capacity, production use) is listed under [Not established by the code](#not-established-by-the-code).

## 1. Overview

Notisbook is a local data workstation for macOS on Apple silicon. One Python process:

- serves a React single-page app and a REST/WebSocket API on `127.0.0.1`;
- manages Jupyter kernels for local Spark, DuckDB and an AWS Glue 6.0 Docker runtime;
- keeps a persistent table catalog in SQLite (Delta, Parquet and Hudi in `spark_catalog`; Iceberg in a JDBC catalog named `iceberg`);
- supervises a local MinIO object store called **notislake**.

Diagrams (Mermaid source):

| View | File |
|---|---|
| System context | [`docs/arch/context.mmd`](arch/context.mmd) |
| Containers | [`docs/arch/container.mmd`](arch/container.mmd) |
| Backend components | [`docs/arch/component.mmd`](arch/component.mmd) |
| Deployment (supporting view) | [`docs/arch/deployment.mmd`](arch/deployment.mmd) |
| Cell execution data flow (supporting view) | [`docs/arch/data-flow.mmd`](arch/data-flow.mmd) |

The HTTP API is described in [`docs/api/swagger.yaml`](api/swagger.yaml) (OpenAPI 3.0). Architectural decisions are recorded in [`docs/adr/`](adr/).

## 2. Repository layout

| Path | Content |
|---|---|
| `backend/` | Python package `notisbook` (hatchling build, Python ≥ 3.12) |
| `backend/src/notisbook/` | Backend source (see section 4) |
| `frontend/` | React 19 + TypeScript SPA built with Vite |
| `scripts/` | `release.sh`, `build_release.py`, `build_minio.py`, `clean.py` |
| `install.sh` | End-user installer and uninstaller |
| `start.sh` | Runs the app from a source checkout |
| `site/` | Static landing page deployed to GitHub Pages (`.github/workflows/pages.yml`) |

## 3. Technology stack

| Layer | Technology | Evidence |
|---|---|---|
| Backend | FastAPI on uvicorn, `jupyter_client`, nbformat, pyiceberg 0.12.0, boto3, nh3, psutil | `backend/pyproject.toml`, `backend/src/notisbook/__main__.py` |
| Frontend | React 19, CodeMirror 6 (Python, SQL, Markdown), zustand 5, DOMPurify, marked, ansi_up, Vite 8, TypeScript 6 | `frontend/package.json` |
| Local Spark | PySpark per environment, built with `uv` (Python 3.12) | `backend/src/notisbook/spark/installer.py` |
| Table formats | Delta Lake, Apache Iceberg, Apache Hudi (pinned jars) | `backend/src/notisbook/spark/bundles.py` |
| DuckDB | Own runtime with offline extensions | `backend/src/notisbook/runtimes/duckdb/` |
| AWS Glue | Docker image `notisbook/glue:6.0` from `aws-glue-libs:6.0` | `backend/src/notisbook/runtimes/docker/catalog.py`, `backend/src/notisbook/runtimes/glue/Dockerfile` |
| Object storage | MinIO (`RELEASE.2025-10-15T17-29-55Z`) | `backend/src/notisbook/notislake/minio_manifest.json` |
| Catalog | SQLite (`catalog.db`) | `backend/src/notisbook/catalog/store.py` |

## 4. Backend components

See [`docs/arch/component.mmd`](arch/component.mmd).

| Package | Responsibility |
|---|---|
| `__main__.py`, `app.py`, `config.py` | CLI, app factory, settings, startup and shutdown |
| `static.py` | Serves the SPA with a Content Security Policy |
| `security.py` | UI, runtime and shutdown tokens; Host and Origin checks |
| `api/` | FastAPI routers for system, contents, sessions (+ WebSocket), catalog, runtime catalog, Iceberg REST, Spark, DuckDB, Docker, jobs (+ WebSocket), notislake, export, files, samples, appearance, lifecycle |
| `kernels/` | `KernelService`, WebSocket protocol v1, hidden in-kernel modules, cell languages |
| `spark/` | Versioned Spark environments, bundle matrix, JDK discovery, jar cache, package management |
| `runtimes/duckdb/` | DuckDB environments, extensions, kernelspec, bootstrap |
| `runtimes/docker/`, `runtimes/glue/` | AWS Glue Docker runtime: image, container, kernel launch |
| `catalog/` | SQLite store, `nb_*` registry, Iceberg JDBC tables, schemas |
| `notislake/` | MinIO binary install, supervisor, credentials, ports, bucket layout, S3A options |
| `notebooks/` | Sandboxed `.ipynb` storage with atomic writes |
| `export/` | Databricks `.py`, `.ipynb` and HTML report export |
| `jobs.py` | In-memory job registry with replayable events |
| `maintenance/` | `update` and `uninstall` commands |
| `onboarding.py`, `preferences.py` | First-run setup and saved preferences |
| `files/`, `fonts/` | Folder listing, native folder picker and font list via `osascript` |

## 5. Process model

### 5.1 Command line

The console script is `notisbook = "notisbook.__main__:main"` (`backend/pyproject.toml`).

| Command | Effect |
|---|---|
| `notisbook [--port N] [--root DIR] [--no-browser]` | Starts the server (default port `8765`) |
| `notisbook --version` | Prints the version |
| `notisbook --check-notislake` | Installs the bundled MinIO into a temporary home and runs `minio --version` |
| `notisbook --stop-running` | Stops the instance registered in the data folder |
| `notisbook update [--version X.Y.Z]` | Updates a `uv tool` installation |
| `notisbook uninstall [--yes]` | Removes the app and keeps user data |

Server options cannot be combined with subcommands (`backend/src/notisbook/__main__.py`).

### 5.2 Startup

From `_serve` in `backend/src/notisbook/__main__.py` and `lifespan` in `backend/src/notisbook/app.py`:

1. Create the data root, `envs/` and `warehouse/`.
2. Create or migrate `catalog.db`.
3. Run onboarding on first run (adopt `~/notebooks` or seed samples).
4. Resolve the notebooks root: `--root` > saved preference > default.
5. Stop a running instance of another version (section 5.4).
6. Bind the socket on `127.0.0.1:<port>`; start the MinIO supervisor (exit on failure).
7. Write `run/backend.json`.
8. Print `http://127.0.0.1:<port>/?token=…` and open the browser after one second unless `--no-browser`.
9. In the ASGI lifespan: remove orphan connection files, reconcile kernelspecs, sweep orphan Docker resources and stale runtimes, empty Spark and DuckDB trash.

### 5.3 Shutdown

The lifespan stops the Spark and DuckDB installers, Docker operations and all kernels, then stops Docker runtimes. After the server exits, owned and running containers are stopped (never removed) within 20 seconds, MinIO is stopped and `run/backend.json` is removed. SIGTERM and SIGHUP trigger the same path (`backend/src/notisbook/__main__.py`, `backend/src/notisbook/app.py`).

### 5.4 Version handover

`<home>/run/backend.json` (mode 0600) holds pid, port, version and a shutdown token. A new process that finds a live instance of a **different** version calls `POST /api/lifecycle/shutdown` with that token and waits up to 60 seconds; the **same** version is refused (`backend/src/notisbook/api/lifecycle.py`).

## 6. Kernels and execution

- Kernels are started with `jupyter_client` (`AsyncKernelManager`), imported only in `backend/src/notisbook/kernels/service.py`.
- Kernelspecs come only from `<home>/kernels`; kernels installed outside the app are refused.
- After a kernel is ready, one silent `execute` installs `_notisbook_display` (SQL and DuckDB result rendering) and `_notisbook_catalog` (Spark patches that keep the catalog in sync and enforce destination rules) (`kernels/sql_cell.py`, `kernels/catalog_hook.py`).
- Cell languages per runtime: local Spark → `python`, `sql`, `duckdb`; DuckDB → `python`, `duckdb`; Docker → `python`, `sql`.
- Stream output is limited to 1 MB per cell with a truncation notice.

### 6.1 WebSocket protocol v1

Defined in `backend/src/notisbook/kernels/protocol.py` and `frontend/src/ws/protocol.ts`. The cell execution path is drawn in [`docs/arch/data-flow.mmd`](arch/data-flow.mmd).

| Direction | Messages |
|---|---|
| Client → server | `execute {cell_id, code, language}`, `interrupt`, `restart` |
| Server → client | `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error` |

Every frame carries `v: 1`. Endpoints: `WS /api/sessions/{session_id}/channel` and `WS /api/jobs/{job_id}/events` (job progress, replayed on every connection). Close codes: 1000 normal, 4404 unknown session, 4409 replaced by a newer connection. The client reconnects with exponential backoff (8 attempts, 500 ms to 10 s) (`frontend/src/ws/socket.ts`).

## 7. Runtimes

### 7.1 Local Spark

- Each install builds an immutable environment `<home>/envs/spark-<version>-<id8>/` with `uv` (Python 3.12, `pyspark`, `ipykernel`, `duckdb==2.0.0`, bundle packages), runs a smoke test, then switches the kernelspec (`spark/installer.py`).
- Offered versions: the 3.5 line and every line from 4.0, newest patch from the PyPI JSON API with an offline fallback list (`spark/catalog.py`).
- JDK: Spark 3.x needs 17; Spark 4.x accepts 21, then 17. Found through `$JAVA_HOME`, `/usr/libexec/java_home` or Homebrew `openjdk@<major>` (`spark/prereqs.py`).
- Bundle matrix with sha256-pinned jars (`spark/bundles.py`):

| Spark line | Delta | Iceberg | Hudi | Scala |
|---|---|---|---|---|
| 3.5.0–3.5.2 | 3.2.0 | 1.10.1 | 1.2.1 | 2.12 |
| 3.5 (patch ≥ 3) | 3.3.3 | 1.10.1 | 1.2.1 | 2.12 |
| 4.1 | 4.1.0 | 1.12.0 | 1.2.1 | 2.13 |

  Lines without an entry (for example 4.0, 4.2, 4.3) get S3A only, without table formats.
- S3A jars are chosen by the Hadoop version inside pyspark (3.3.4, 3.4.1, 3.4.2, 3.5.0); an unknown version fails the install.
- Jars come from Maven Central (override `NOTISBOOK_MAVEN_URL`) into a content-addressed cache `<home>/jars/<sha256>/`.
- Per-environment libraries are installed with `uv pip`, PyPI only, with validated requirement strings (`spark/packages.py`, `spark/requirements.py`).

### 7.2 AWS Glue 6.0 (Docker)

- One catalog entry: key `glue`, label "AWS Glue 6.0", image `notisbook/glue:6.0`, container `notisbook-glue`, kernel `notisbook-docker-glue` (`runtimes/docker/catalog.py`).
- The image is built locally from `public.ecr.aws/glue/aws-glue-libs:6.0` pinned by digest, adding `ipykernel` (`runtimes/glue/Dockerfile`). A Dockerfile comment states Spark 4.1, Scala 2.13, Python 3.13 and Java 17.
- The build requires at least 15 GiB free and has a one-hour timeout.
- The container runs with `--init --network host --cap-drop ALL --security-opt no-new-privileges --user hadoop` and app-owner labels. Mounts must be inside `$HOME`, outside credential folders (`.aws`, `.ssh`, `.gnupg`, `.kube`, `.docker`) and outside the data folder except `notebooks/` and `warehouse/` (`runtimes/docker/service.py`).
- Kernels start with `docker exec`; the connection file goes through stdin. Spark inside the container uses the backend's Iceberg REST catalog at `http://host.lima.internal:<port>/iceberg` and `/api/runtime-catalog` for the registry.

### 7.3 DuckDB

- Immutable environment `<home>/envs/duckdb-<version>-<id>/` and kernel `duckdb-<maj>-<min>-<patch>`.
- Versions in the manifest: 2.0.1 and 1.5.6. Extensions httpfs, iceberg, avro, excel, sqlite_scanner, postgres_scanner and spatial, for `osx_arm64`, verified twice by sha256 (`runtimes/duckdb/extensions.json`, `runtimes/duckdb/installer.py`).
- At kernel start: temporary S3 and Iceberg secrets, then `ATTACH 'notislake' (TYPE iceberg, ENDPOINT 'http://127.0.0.1:<port>/iceberg')` (`runtimes/duckdb/hook.py`).

## 8. Catalog

- One SQLite file, `<home>/catalog.db`, in WAL mode with migrations by `PRAGMA user_version` (`catalog/store.py`).
- `spark_catalog` registry (`nb_namespaces`, `nb_tables`, `nb_meta`) for Delta, Parquet and Hudi tables; every write increments `generation` so open sessions reconcile (`catalog/registry.py`).
- Iceberg JdbcCatalog `iceberg` with tables `iceberg_tables` and `iceberg_namespace_properties`, created by the backend (`catalog/iceberg_jdbc.py`).
- Schemas `bronze`, `silver` and `gold` exist in both catalogs and cannot be dropped.

How each runtime reaches the catalog:

| Runtime | Registry (`nb_*`) | Iceberg |
|---|---|---|
| Local Spark | SQLite, directly from the hook | JDBC over `catalog.db` |
| Glue (Docker) | HTTP `/api/runtime-catalog` | Iceberg REST `/iceberg` |
| DuckDB | — | Iceberg REST `/iceberg` |

## 9. Storage (notislake)

- MinIO package: from `$NOTISBOOK_MINIO_DIST`, else `~/.local/share/notisbook/notislake` (placed by `install.sh`). Verified against `minio_manifest.json` and installed to `<home>/minio/bin/`. The backend never downloads it (`notislake/binary.py`).
- Supervisor: one per data folder (`flock`), two free loopback ports chosen at start, restart backoff 1/2/4/8/16 s, `failed` state on crash loops, log rotation at 10 MB (`notislake/supervisor.py`, `notislake/ports.py`).
- Bucket `notislake` with prefixes `landing/`, `bronze/`, `silver/`, `gold/` (`notislake/locations.py`).
- Credentials are generated once into `<home>/minio/credentials.json` (0600) and passed to MinIO only through its environment.
- A manual S3-compatible connection can replace the local store (`<home>/notislake-connection.json`, 0600).
- Spark environments carry closed S3A defaults on disk; real per-bucket options are injected per session. New sessions are refused with 503 `notislake_unavailable` when storage is not running.

## 10. Data root

`$NOTISBOOK_HOME` or `~/.notisbook` (`config.py`):

| Path | Content |
|---|---|
| `catalog.db` | Catalog |
| `envs/` | Spark and DuckDB environments |
| `kernels/` | App-managed kernelspecs |
| `jars/` | Jar cache |
| `minio/` | MinIO binary, data, logs, credentials |
| `run/backend.json` | Running instance record |
| `preferences.json` | Notebooks root and onboarding state |
| `notebooks/` | Default notebooks root |
| `warehouse/`, `spark-warehouse/` | Safety warehouses for Docker and local Spark |

On first run the app seeds samples: `spark/{delta,hudi,iceberg}.ipynb`, `glue/{delta,hudi,iceberg}.ipynb` and `duckdb/duckdb.ipynb` (`onboarding.py`, `samples/`).

## 11. Security controls

| Control | Implementation | Evidence |
|---|---|---|
| Network exposure | Bind to `127.0.0.1` only, not configurable | `config.py` |
| UI authentication | Random token per process; Bearer, cookie `notisbook_token` or `?token=` (sets an `HttpOnly; SameSite=Strict` cookie) | `security.py` |
| Runtime authentication | Per-session tokens for Docker and DuckDB kernels, valid only on `/api/runtime-catalog` and `/iceberg` | `security.py`, `kernels/service.py` |
| Shutdown | Separate token, loopback clients only | `api/lifecycle.py` |
| DNS rebinding | Host allow-list; WebSockets also check `Origin` | `security.py`, `config.py` |
| Content Security Policy | `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'` | `static.py` |
| Output sanitization | DOMPurify for HTML, Markdown and ANSI outputs; HTML outputs in a Shadow DOM; nh3 for HTML export | `frontend/src/components/outputs/purify.ts`, `export/html_report.py` |
| Secret handling | Credentials never in argv, `kernel.json` or logs; access log disabled because the token travels in the URL | `notislake/supervisor.py`, `__main__.py` |
| Supply chain | sha256 pins for jars, MinIO, DuckDB extensions, `install.sh`; Glue base image pinned by digest | `spark/bundles.py`, `notislake/minio_manifest.json`, `runtimes/glue/Dockerfile` |
| Container hardening | `--cap-drop ALL`, `no-new-privileges`, non-root user, restricted mounts | `runtimes/docker/service.py` |

Not every router checks the Host header: contents, sessions, Spark, DuckDB, export and jobs rely on the token only. `GET /api/notislake/local/credentials` returns the local MinIO credentials to the authenticated UI.

## 12. Frontend

- React 19 SPA with CodeMirror 6; routing uses the History API without a library (`frontend/src/state/router.ts`).
- Global zustand stores per area, plus a notebook store and a kernel store per open notebook (`frontend/src/state/`).
- The API client uses relative `/api` paths. The token from `?token=` is exchanged for the cookie at `/api/health` and removed from the URL (`frontend/src/api/auth.ts`).
- In development, Vite runs on port 5173 and proxies `/api` (including WebSockets) to `127.0.0.1:8765` (`frontend/vite.config.ts`).

## 13. Build, distribution and release

See [`docs/arch/deployment.mmd`](arch/deployment.mmd).

- `scripts/build_release.py` builds the frontend, copies it into `backend/src/notisbook/_frontend`, builds the wheel and sdist with `uv build`, exports `constraints-<v>.txt`, checks that all pins have binary wheels for Python 3.12 on `aarch64-apple-darwin`, and writes `SHA256SUMS`.
- `scripts/build_minio.py` compiles `minio` and `mc` from pinned tags in Docker (`golang:1.24.13`) for `darwin/arm64` and updates the manifest.
- `scripts/release.sh [--dry-run | --local-install] X.Y.Z` checks the tree (branch `main`, clean, equal to `origin/main`, CHANGELOG section present), sets the version, commits, tags, builds, pushes and creates the GitHub release. Assets: wheel, constraints, MinIO tarball, `SHA256SUMS`, `install.sh` (the sdist is not uploaded).
- `install.sh` accepts macOS on Apple silicon only, installs `uv` 0.10.8 if missing (minimum 0.8.4), verifies downloads with `shasum -a 256 -c`, runs `uv tool install --python 3.12 --no-build` and places the MinIO tarball.
- `notisbook update` downloads `install.sh` and `SHA256SUMS` from the release, verifies the script and runs it; downgrades are refused.
- `notisbook uninstall` removes environments, kernels, jars, logs, the MinIO package and the tool; it keeps `minio/data`, credentials, `catalog.db`, warehouses, preferences and notebooks.
- CI: only `.github/workflows/pages.yml`, which deploys `site/` to GitHub Pages. There is no CI for tests, lint or releases.

## 14. Platform

macOS on Apple silicon, native or under Rosetta (`platform_support.py`, `install.sh`). The Docker runtime expects a Colima-style host (`host.lima.internal`, only `$HOME` shared).

## 15. External systems

| System | Purpose |
|---|---|
| GitHub Releases (`ROM-mm/Notisbook`) | Installation and updates |
| PyPI | Spark version list; pyspark, duckdb and user libraries via `uv` |
| Maven Central | Lakehouse and S3A jars |
| `extensions.duckdb.org` | DuckDB extensions |
| Amazon ECR Public | `aws-glue-libs:6.0` base image |
| Docker daemon (Colima) | Glue runtime |
| Optional S3-compatible endpoint | Replacement for the local MinIO |
| macOS (`java_home`, Homebrew, `osascript`, `sysctl`) | JDK discovery, folder picker, fonts, Rosetta detection |

## Not established by the code

- Performance, memory use or capacity figures.
- Whether Spark 4.0, 4.2 and 4.3 install successfully: it depends on the Hadoop version in each pyspark wheel.
- Component versions inside the Glue 6.0 image, beyond a Dockerfile comment.
- The full internal behavior of the Iceberg REST implementation and of the catalog hook (only partially analyzed).
- Spark environments pin `duckdb==2.0.0` for DuckDB cells, while the DuckDB runtime manifest lists 2.0.1 and 1.5.6; the reason is not stated.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
