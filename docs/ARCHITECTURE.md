# Notisbook Architecture

## Scope and sources

This document describes the structure observed in the repository's code and configuration (`backend/`,
`frontend/`, `install.sh`, `start.sh` and `scripts/`), by static reading. It does not prove runtime behavior:
Notisbook is a local desktop application and the repository holds no server deployment definition. Items without
evidence are marked as `Not identified in the analyzed code`. Paths below are relative to
`backend/src/notisbook/` unless they start with a top-level folder.

Diagrams (Mermaid, in `docs/arch/`):

| View | File |
|---|---|
| Context | [context.mmd](arch/context.mmd) |
| Containers | [container.mmd](arch/container.mmd) |
| Backend components | [component.mmd](arch/component.mmd) |
| Local deployment | [deployment.mmd](arch/deployment.mmd) |
| Data flow | [data-flow.mmd](arch/data-flow.mmd) |

Architectural decisions are in [docs/adr/](adr/) and the HTTP contract is in [docs/api/swagger.yaml](api/swagger.yaml).

## Overview

Notisbook is one Python process (FastAPI + Uvicorn, Python ≥ 3.12) that serves a compiled React SPA and exposes a
REST API and WebSockets on `127.0.0.1`. The same process:

- starts and supervises a local MinIO, the **notislake** (`notislake/supervisor.py`);
- starts Jupyter kernels through `jupyter_client` for three runtimes: local Spark, DuckDB and AWS Glue in Docker
  (`kernels/service.py`);
- keeps the table catalog in SQLite (`catalog.db`, `catalog/store.py`) and serves an Iceberg REST catalog over it
  (`api/iceberg_rest.py`);
- installs runtimes and Python libraries as background jobs with progress over WebSocket (`jobs.py`, `api/jobs.py`).

Supported platform: macOS on Apple silicon, native or Python under Rosetta (`platform_support.py:12-27`). On an
Intel Mac the MinIO package is refused (`notislake/binary.py:112-121`) and startup exits with an error
(`__main__.py:197-206`, chain inferred statically).

## Components

### Backend (`backend/src/notisbook/`)

| Module | Responsibility |
|---|---|
| `__main__.py` | CLI (`notisbook`, `update`, `uninstall`), startup/shutdown sequence |
| `app.py`, `static.py` | FastAPI app, routers, `X-Notisbook: 1` header, SPA serving with CSP; `/docs`, `/redoc` and `/openapi.json` disabled |
| `config.py`, `security.py` | Data folder, bind/port, UI token, runtime tokens, Host/Origin checks |
| `api/` | REST and WebSocket routers (contents, sessions, catalog, runtime-catalog, iceberg, spark, duckdb, docker, notislake, files, export, samples, system, appearance, notebooks-root, lifecycle, jobs) |
| `kernels/` | Kernel sessions (`service.py`), WebSocket protocol v1 (`protocol.py`), cell languages, hidden display module (`sql_cell.py`) and catalog hook (`catalog_hook.py`) |
| `spark/` | Spark version catalog, lakehouse bundle matrix, JDK detection, environment installer, kernelspecs, library management |
| `runtimes/duckdb/` | DuckDB environment, pinned extensions (`extensions.json`), kernelspec and bootstrap hook |
| `runtimes/docker/`, `runtimes/glue/` | AWS Glue 5.0 image (`Dockerfile`), shared container, `docker exec` launcher |
| `catalog/` | `catalog.db` schema and migrations, registry (reconcile plans), Iceberg JDBC tables, schemas, Catalog info |
| `notislake/` | MinIO binary install from a sha256 manifest, supervisor, ports, credentials, bucket bootstrap, S3A configuration, manual connection settings |
| `notebooks/`, `files/` | Contents store confined to the notebooks root; folder browser and native macOS folder picker |
| `export/` | `.py` (Databricks source), `.ipynb` and HTML report |
| `maintenance/` | `update` and `uninstall` commands, `uv tool` environment detection |
| `onboarding.py`, `preferences.py`, `samples/` | First run, notebooks root preference, bundled sample notebooks |

### Frontend (`frontend/`)

React 19 + TypeScript built by Vite 8, state in `zustand`, editor on CodeMirror 6, Markdown via `marked` +
`dompurify`, ANSI via `ansi_up` (`frontend/package.json`). Routing uses the History API (`src/state/router.ts`):
`/` (Home), `/tree/<dir>`, `/notebooks/<path>`, `/settings` (Runtimes; `/spark` is a legacy alias) and
`/settings/appearance`.

- **Home** (`src/App.tsx`): examples from `/api/samples` with the runtime each one needs, *Get started* only while
  no runtime is installed, *New notebook*, the 5 most recent notebooks per root and *Browse notebooks…*.
- **AppShell** (`src/components/shell/`): banner with the menu (File, Edit, View, Run, Settings, Help), notebook
  tabs and the kernel toolbar; left sidebar (Catalog, Notislake), right sidebar (Notebooks), Catalog info / Table
  info panel, footer with shortcuts and RAM/CPU/Disk; focus mode (⌘.) hides both sidebars.
- **Settings › Runtimes** (`src/components/spark/SparkSettings.tsx`): prerequisites/JDK, Spark versions and
  libraries, AWS Glue Docker runtime and DuckDB.
- **Settings › Appearance** (`src/components/appearance/`): Interface, Code cell and Markdown fonts, saved only in
  `localStorage` (`notisbook.appearance`); system fonts come from `/api/appearance/system-fonts`.
- Output rendering order: `text/html` > PNG > JPEG > SVG > `text/markdown` > `text/plain`; JavaScript and ipywidgets
  outputs are not rendered (`src/components/outputs/mime.ts`).
- Local folders in the files browser are disabled in the UI (`LOCAL_FOLDERS_ENABLED = false`,
  `src/state/files.ts:11`); the `/api/fs/*` routes remain in the backend.

The compiled frontend is copied into `backend/src/notisbook/_frontend/` and shipped inside the wheel
(`scripts/build_release.py`). `NOTISBOOK_FRONTEND_DIST` or an existing `frontend/dist` take precedence in
development (`config.py:39-47`).

## Runtimes

| Runtime | Environment | Cell languages | Catalog access |
|---|---|---|---|
| Local Spark | `<home>/envs/spark-<version>-<id>/`, Python 3.12, `pyspark`, `ipykernel`, `duckdb==2.0.0`, bundle jars | `python`, `sql`, `duckdb` | Catalog hook writes `catalog.db` (SQLite); Iceberg via JDBC catalog |
| DuckDB | `<home>/envs/duckdb-<version>-<id>/`, `duckdb==2.0.1`, `ipykernel`, pinned extensions | `python`, `duckdb` | Iceberg REST at `http://127.0.0.1:<port>/iceberg` |
| AWS Glue 5.0 (Docker) | Image `notisbook/glue:5.0` from the pinned AWS Glue base image; container `notisbook-glue-5-0` | `python`, `sql` | HTTP `/api/runtime-catalog` and Iceberg REST `/iceberg` via `host.lima.internal` |

Cell languages come from one backend table exposed as `cell_languages` in `/api/kernelspecs`
(`kernels/service.py:186-193`); an unsupported language is refused before reaching the kernel.

### Local Spark

- Version list: stable `pyspark` releases from PyPI in the last 180 days, with a static fallback
  (`spark/catalog.py`).
- JDK: 17 for Spark 3.x; 21 (or 17) for other lines; searched in `JAVA_HOME`, `/usr/libexec/java_home` and Homebrew
  `openjdk@<major>` (`spark/prereqs.py:132-203`).
- Install phases: prereqs → python → venv → install → bundle → validate → kernelspec → cleanup. Validation runs a
  smoke test with a throwaway `catalog.db`; the kernelspec is switched only after validation and a failure deletes
  the new environment (`spark/installer.py:380-401`).
- Bundle matrix (`spark/bundles.py:97-182`, revision 4), every artifact checked by sha256 before use:

  | Line | Delta | Iceberg | Hudi | S3A |
  |---|---|---|---|---|
  | 3.5.0–3.5.2 | 3.2.0 | 1.10.1 | 1.2.1 | `hadoop-aws` 3.3.4, AWS SDK v1 1.12.262 |
  | 3.5.3+ | 3.3.3 | 1.10.1 | 1.2.1 | `hadoop-aws` 3.3.4, AWS SDK v1 1.12.262 |
  | 4.1 | 4.1.0 | 1.12.0 | 1.2.1 | `hadoop-aws` 3.4.2, AWS SDK v2 2.29.52 |

  A version without a bundle installs Spark only and its kernel is refused with `spark_env_outdated`
  (`spark/installer.py:436-442`, `kernels/service.py:915-922`). Observed: the static fallback suggests `4.3.0`, which
  has no bundle (`spark/catalog.py:18`).
- `spark-defaults.conf` and `log4j2.properties` are rewritten when a kernel opens: in-memory Spark catalog, Delta,
  Iceberg and Hudi extensions, closed S3A defaults and Spark logs reduced to errors (`spark/bundles.py`).
- Libraries: `uv pip install/uninstall` with a filtered environment; URLs, extras and direct references are refused
  and base libraries are protected; no change is allowed while a session is active (`spark/packages.py`,
  `spark/requirements.py`, `api/spark.py`).

### DuckDB

Own kernel named `duckdb`. Extensions httpfs, iceberg, avro, excel, sqlite_scanner, postgres_scanner and spatial
are downloaded for `osx_arm64` and checked by sha256 (`runtimes/duckdb/extensions.json`); autoinstall and autoload
are off. At kernel start a silent execute creates S3 and Iceberg secrets and runs
`ATTACH 'notislake' (TYPE iceberg, ENDPOINT http://127.0.0.1:<port>/iceberg)` with a per-session token
(`runtimes/duckdb/hook.py`).

### AWS Glue 5.0 in Docker

- Base image `public.ecr.aws/glue/aws-glue-libs:5@sha256:a54bd25f…4f01` (Spark 3.5, Python 3.11, Java 17); the
  derived image adds `ipykernel` and runs as `hadoop` (`runtimes/glue/Dockerfile`). The build needs about 15 GiB.
- One shared container: `docker run -d --init --network host --cap-drop ALL --security-opt no-new-privileges`,
  owner labels, bind mounts at the same Mac paths for the notebooks root and `<home>/warehouse`
  (`runtimes/docker/service.py:472-488`). A container with the same name but without the labels is left untouched.
  `$HOME` itself, folders outside it, `.aws`, `.ssh` and the data folder are refused as mounts.
- Each session is a `docker exec` of an ipykernel inside the container (`runtimes/docker/launch.py`).
- Formats: Delta and Iceberg; Hudi is not registered by this runtime (`kernels/catalog_hook.py:44`).

## Kernels and the catalog hook

- `jupyter_client` (`AsyncKernelManager`) is used only in `kernels/service.py`. Connection files go to
  `jupyter_runtime_dir()/notisbook/` (0700). `SPARK_HOME`, `PYTHONPATH` and `PYSPARK_*` are removed from the kernel
  environment.
- WebSocket protocol v1 at `/api/sessions/{id}/channel` (`kernels/protocol.py`): the client sends `execute`
  (`cell_id`, `code`, `language`), `interrupt` and `restart`; the server sends `status`, `execute_input`, `output`,
  `clear_output`, `execute_reply` and `error`. A new socket replaces the previous one; streams are capped at 1 MB per
  cell.
- When a kernel is ready, a silent execute installs the hidden modules `_notisbook_display` and
  `_notisbook_catalog` (reinstalled only when their sha1 changes):
  - `echo(df, n=...)` renders DataFrames (default 50 rows, max 1000); `display` is not available in cells. SQL cells
    use the active session and never call `getOrCreate` (`kernels/sql_cell.py`).
  - The catalog hook patches `SparkSession` creation, DataFrame writers, `Catalog.createTable` and `SparkSession.sql`,
    checks the destination before writing and reconciles the catalog after each cell (`post_run_cell`); before each
    cell it imports what other kernels recorded (`pre_run_cell`). It applies the real S3A credential after
    `getOrCreate`, never in argv (`kernels/catalog_hook.py`).
  - Spark/JVM startup output is held back and the Ivy resolution log is summarized.

## Catalog

`<home>/catalog.db` (SQLite, WAL, migrations by `PRAGMA user_version`, created at startup):

| Table | Content |
|---|---|
| `iceberg_tables`, `iceberg_namespace_properties` | Iceberg JDBC catalog (schema V1) |
| `nb_namespaces` | Schemas of `spark_catalog`, with a display group (`spark_catalog` or `hudi`) |
| `nb_tables` | Delta, Parquet and Hudi tables, `MANAGED` or `EXTERNAL`, with Delta version / Hudi instant |
| `nb_meta` | `generation` counter that sessions use to reconcile |

- Catalogs: `spark_catalog` (`DeltaCatalog`) for Delta, Parquet and Hudi; `iceberg` named catalog (JDBC over
  `catalog.db`, warehouse `s3a://notislake`, `gc.enabled=false`); `hudi` is a display node only
  (`catalog/registry.py:18-19`, `spark/bundles.py:254-269`).
- Layers: schemas `bronze`, `silver` and `gold` are seeded in both catalogs and cannot be dropped; a managed table
  lives at `s3a://notislake/<layer>/<table>`; `landing` is a free zone, not a layer (`notislake/locations.py`).
- DROP by format: Delta/Parquet/Hudi `MANAGED` → the registry returns the folder and the **kernel** deletes it;
  `EXTERNAL` → only the registry row is removed; Iceberg → registry only unless `PURGE`; through Iceberg REST, purging
  an `s3a` table is refused. The backend itself never deletes table files.
- Catalog info (`GET /api/catalog/info`) and Table info (`GET /api/catalog/table`) work without a kernel; sensitive
  configuration values are masked by the backend (`catalog/catalog_info.py`).
- Writers: local kernels write SQLite directly; the Docker runtime and DuckDB go through the backend
  (`/api/runtime-catalog/plan`, `/iceberg`), so the container never opens `catalog.db`.

## notislake (local MinIO)

- Binary: `minio` and `mc` built by `scripts/build_minio.py` for `darwin-arm64`, shipped as a tarball described by
  `notislake/minio_manifest.json` (tag, commits, sha256). The backend installs only from `NOTISBOOK_MINIO_DIST` or
  `${XDG_DATA_HOME:-~/.local/share}/notisbook/notislake`, checking the tarball and binaries, into
  `<home>/minio/bin/` (`notislake/binary.py`).
- Supervisor: one per data folder (`flock` on `<home>/minio/run/notislake.lock`), started in `main()`; two free
  loopback ports (API and console); readiness on `/minio/health/ready` (30 s); restarts with backoff 1–16 s; log at
  `<home>/minio/logs/minio.log` rotated at 10 MB (`notislake/supervisor.py`).
- Bucket `notislake` with prefixes `bronze/`, `silver/` and `gold/`, created with boto3 (`notislake/bootstrap.py`).
- Credentials in `<home>/minio/credentials.json` (0600), passed to MinIO only through the process environment.
  `GET /api/notislake/local/credentials` returns them to the UI (*Copy credentials* in the Notislake panel menu).
- Automatic vs. manual: a valid `<home>/notislake-connection.json` (0600) selects a manual S3 endpoint; otherwise the
  local MinIO is used. In automatic mode a new session fails closed if MinIO is not `running`
  (`notislake/objectstore.py`, `kernels/service.py:773-793`).
- S3A uses only per-bucket keys `fs.s3a.bucket.notislake.*`; for the Docker runtime the loopback endpoint is
  rewritten to `host.lima.internal` (`notislake/sparkconf.py`).

## Configuration and data folder

| Variable | Effect |
|---|---|
| `NOTISBOOK_HOME` | Data folder (default `~/.notisbook`) |
| `NOTISBOOK_MINIO_DIST` | MinIO package folder or tarball |
| `XDG_DATA_HOME` | Base of the default MinIO package folder (absolute values only) |
| `NOTISBOOK_FRONTEND_DIST` | Frontend folder served |
| `NOTISBOOK_PYPI_URL` | PyPI URL (default `https://pypi.org`) |
| `NOTISBOOK_MAVEN_URL` | Maven repository for bundle jars (default Maven Central) |
| `NOTISBOOK_INSTALL_FROM` | Local folder with release assets for `install.sh` and `notisbook update` |

Data folder layout (`<home>`):

| Path | Content |
|---|---|
| `envs/` | Spark and DuckDB environments |
| `catalog.db` | Table catalog |
| `notebooks/` | Default notebooks root, seeded with samples on the first run |
| `warehouse/`, `spark-warehouse/` | Local warehouse paths (mounted in the Glue container / safety fallback) |
| `minio/` | `bin/`, `data/`, `logs/`, `run/`, `credentials.json` |
| `notislake-connection.json` | Manual S3 connection (0600) |
| `preferences.json` | Notebooks root and `samples_seeded` (0600) |
| `run/backend.json` | Running instance record `{pid, port, version, token}` (0600) |

Notebooks root precedence: `--root` (locks the UI), saved preference, `<home>/notebooks`. First run (no
`preferences.json`): an existing `~/notebooks` with notebooks is adopted when `NOTISBOOK_HOME` is not set; otherwise
the bundled samples are copied without overwriting (`onboarding.py`).

## Lifecycle

Startup (`__main__.py:296-366`): create the data folder and `catalog.db` → onboarding → resolve the notebooks root →
stop a previous instance → bind `127.0.0.1:<port>` → start the notislake → write `run/backend.json` → print the URL
with the token and open the browser → run Uvicorn (access log off so the token is not printed).

Version handover (`api/lifecycle.py:212-231`): a stale record is removed; a running instance of a **different**
version receives `POST /api/lifecycle/shutdown` with its own token and Notisbook waits up to 60 s for it to exit; the
**same** version running makes startup fail. `--stop-running` stops the registered instance of any version.

Shutdown: installers, kernels and Docker runtimes are stopped, catalog containers are stopped (not removed), MinIO is
stopped and the instance record is removed only by its own process.

## Distribution and maintenance

- Release assets: wheel `notisbook-<v>-py3-none-any.whl` (frontend embedded), `constraints-<v>.txt` exported from
  `uv.lock`, the MinIO tarball for `darwin-arm64`, `SHA256SUMS` and `install.sh` (`scripts/release.sh`). The build
  enforces binary wheels for `aarch64-apple-darwin` so nothing is compiled on the user's Mac
  (`scripts/build_release.py`).
- `install.sh`: macOS Apple silicon only; verifies sha256 before changing anything; installs with
  `uv tool install --force --managed-python --no-build -c constraints` on Python 3.12; places the MinIO tarball and
  runs `notisbook --check-notislake`.
- `notisbook update [--version]` (`maintenance/update.py`): works only inside the `uv tool` environment, resolves the
  target release, refuses downgrades (because of the `catalog.db` schema), downloads `install.sh` and `SHA256SUMS`
  over HTTPS, verifies `install.sh` and executes it.
- `notisbook uninstall [--yes]` (`maintenance/uninstall.py`): lists what is removed and kept, asks for confirmation,
  stops the instance, removes the app-owned Glue container, kernelspecs, `envs/`, MinIO binaries/logs and run files,
  then runs `uv tool uninstall notisbook`. Kept: `minio/data`, credentials, `catalog.db`, warehouses, preferences,
  notebooks, manual connection and Docker images.
- `scripts/release.sh --local-install <X.Y.Z>` builds a version and installs it on the developer's Mac through
  `install.sh` from `backend/dist/local-<X.Y.Z>/`, outside the active Python environment, without committing,
  tagging or publishing.
- The landing page in `site/` is published to GitHub Pages by `.github/workflows/pages.yml`, independently of app
  releases.

## Security controls

| Control | Evidence |
|---|---|
| Fixed bind on `127.0.0.1` | `config.py:11-12` |
| UI token per startup (`Authorization: Bearer`, `notisbook_token` cookie `HttpOnly; SameSite=Strict`, or `?token=`), compared in constant time | `security.py:14-46` |
| Host check (`127.0.0.1:<port>`, `localhost:<port>`) against DNS rebinding | `security.py:102-106` |
| WebSocket: token, `Origin` and `Host` checked before accept | `security.py:109-130` |
| Runtime tokens per Docker/DuckDB session, in memory only, accepted only on `/api/runtime-catalog` and `/iceberg` (Host may also be `host.lima.internal`) | `security.py:62-99` |
| Shutdown only from loopback with the token in `run/backend.json` | `api/lifecycle.py:256-271` |
| Strict CSP on the SPA (`script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`) | `static.py:12-17` |
| HTML export sanitized with `nh3`, no JavaScript, `CSP: sandbox` on the response | `export/html_report.py`, `api/export.py` |
| Notebooks store confined to the root (no `..`, absolute paths or escaping symlinks) | `notebooks/store.py:101-116` |
| Folder deletion policy (no root, home, data folder, hidden folders, active root; 409 with open kernel or catalog tables) | `files/browser.py:123-182`, `api/files.py:52-75` |
| Glue container hardened (`--cap-drop ALL`, `no-new-privileges`, non-root user, restricted mounts) | `runtimes/docker/service.py` |
| Secret files written with mode 0600 | `preferences.py`, `notislake/credentials.py`, `api/lifecycle.py` |

Observed: the `contents`, `export`, `sessions`, `spark`, `duckdb` and `jobs` routers and `GET /api/health` check the
UI token but not the Host header. Configured controls do not prove operational guarantees; no external security
review is identified in the repository.

## Not identified in the analyzed code

- Automated tests for backend or frontend (the frontend has no test script).
- CI building or publishing the application (only the GitHub Pages workflow exists).
- Iceberg version inside the AWS Glue image (comments mention 1.7.1; not verified).
- Performance or capacity figures.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
