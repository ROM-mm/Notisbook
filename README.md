<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/favicon-dark.svg">
  <img alt="Notisbook" src="frontend/public/favicon-light.svg" width="96" height="96">
</picture>

# Notisbook — Process anything. Locally.

A local data workstation for `.ipynb` notebooks. Run Python, Spark SQL and DuckDB SQL cells on three runtimes —
local Spark, DuckDB and AWS Glue 5.0 in Docker — over a local MinIO lake (the **notislake**) organized in
`bronze`, `silver` and `gold` layers, with a persistent table catalog. Everything runs on your Mac: the backend
listens on `127.0.0.1` only.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Release](https://img.shields.io/github/v/release/ROM-mm/Notisbook)](https://github.com/ROM-mm/Notisbook/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20Apple%20silicon-lightgrey)](#requirements)

[Releases](https://github.com/ROM-mm/Notisbook/releases) • [Architecture](docs/ARCHITECTURE.md) • [ADRs](docs/adr/) • [HTTP API](docs/api/swagger.yaml)

</div>

---

## The problem it solves

Trying Delta Lake, Apache Iceberg, Apache Hudi or an AWS Glue job locally usually means assembling a Spark
installation, matching jar versions, a JDK, an S3-compatible store and a metastore by hand. Notisbook packages that
setup: it installs each runtime in an isolated, verified environment, starts the object store for you and keeps
track of the tables your notebooks create — without any cloud account or remote service.

## How it works

`notisbook` is a single local process (FastAPI) that serves a browser UI and:

- starts Jupyter kernels for the runtime you choose in each notebook;
- starts and supervises a local MinIO that serves the `notislake` bucket (`s3a://notislake/<layer>/<table>`);
- records every table written by a notebook in a SQLite catalog (`catalog.db`), shown in the **Catalog** panel
  without opening a Spark session;
- serves an Iceberg REST endpoint so DuckDB and the Glue container use the same Iceberg catalog.

## What's in the box

| Capability | What it means |
|---|---|
| **Notebook editor** | `.ipynb` (nbformat v4) with code and markdown cells. Code cells run `python`, `sql` (Spark SQL) or `duckdb`; the language menu only offers what the selected kernel runs. Run with Shift+Enter or ⌘Enter, Run all, Interrupt, Restart, Restart and run all, Clear all outputs. |
| **Spark runtime** | Each Spark version lives in its own immutable environment (Python 3.12 via `uv`, `pyspark`, `ipykernel`, `duckdb`) registered as a kernel. A failed install keeps the previous environment. |
| **Lakehouse bundles** | A static matrix per Spark line (3.5 and 4.1) pins Delta Lake, Iceberg, Hudi and Hadoop S3A jars, each checked by sha256. Delta, Parquet and Hudi tables live in `spark_catalog`; Iceberg lives in a named `iceberg` catalog. |
| **DuckDB runtime** | A separate kernel with DuckDB and pinned extensions (httpfs, iceberg, avro, excel, sqlite, postgres, spatial). It reads and writes Iceberg tables in the notislake through the backend's Iceberg REST catalog. |
| **AWS Glue runtime** | Optional Docker runtime based on the AWS Glue 5.0 image (Spark 3.5, Python 3.11, Java 17) with Delta and Iceberg, in a shared local container. The container reaches the catalog only through the backend API. |
| **notislake** | A local MinIO started and supervised by Notisbook. The schema decides the layer: tables go to `bronze`, `silver` or `gold`. A manual S3 endpoint can be configured instead (**Settings** in the Notislake panel menu). |
| **Catalog panel** | Catalog → schema → table → columns, read from `catalog.db`. **Catalog info** and **Table info** panels show configuration and metadata without a kernel; create and delete schemas from the UI. |
| **Library management** | Install, upgrade and remove Python libraries of a Spark environment from **Settings › Runtimes**, with `uv pip`. Base libraries are protected. |
| **Export** | **File** menu → `.ipynb`, `.py` (Databricks *notebook source*: `echo(df)` becomes `display(df)`) and a self-contained HTML report without JavaScript. Export works on the notebook in memory; nothing is written to disk. |
| **Workspace** | Home with examples and recent notebooks, notebook tabs, left (Catalog, Notislake) and right (Notebooks) sidebars, focus mode (⌘.), light/dark themes and font choices in **Settings › Appearance** (⌘,). |
| **Local-only access** | Fixed `127.0.0.1` bind, a random token per startup, `Host`/`Origin` checks, a strict CSP and sanitized HTML outputs. |

Inside a notebook, show a DataFrame with `echo(df)` (up to 50 rows by default, `n=` up to 1000). A bare DataFrame
as the last expression and SQL/DuckDB cells render as tables too.

## Requirements

- A Mac with **Apple silicon** (arm64). Intel Macs are not supported; Python under Rosetta uses the arm64 artifacts.
- `curl` (or `wget`), `awk` and `shasum` for the installer.
- `uv` 0.8.4 or newer; if it is missing, the installer installs `uv` 0.10.8.
- To install Spark runtimes: JDK 17 for Spark 3.x; JDK 21 (or 17) for Spark 4.x. Notisbook looks in `JAVA_HOME`,
  `/usr/libexec/java_home` and Homebrew `openjdk@<major>`.

### Optional: AWS Glue Docker runtime

- Docker (for example via Colima), with about 15 GiB of free disk space for the image build.
- The AWS Glue base image, pinned by digest in `backend/src/notisbook/runtimes/glue/Dockerfile`:

  ```bash
  docker pull public.ecr.aws/glue/aws-glue-libs:5@sha256:a54bd25fb72c55a2f28d07656a3cda943a042f345cc25f4c2c170667be864f01
  ```

## Quick start

```bash
curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh | sh
notisbook
```

The installer checks the sha256 of every file against the release's `SHA256SUMS` before installing anything, stops
a running Notisbook, installs the wheel with `uv tool install --no-build` on Python 3.12 and places the MinIO package
in `~/.local/share/notisbook/notislake`. The `notisbook` command lives in the `uv tool` bin directory (usually
`~/.local/bin`); if it is not on your `PATH`, the installer tells you how to add it.

`notisbook` starts the backend on `http://127.0.0.1:8765`, prints the address with a per-startup token
(`/?token=<token>`) and opens your browser. Then:

1. **Get started** — open **Settings › Runtimes** and install a Spark version, DuckDB or the AWS Glue image.
2. **Examples** — on the first run, `~/.notisbook/notebooks` is seeded with `delta.ipynb`, `iceberg.ipynb`,
   `hudi.ipynb`, `duckdb.ipynb` and `glue.ipynb`. Open one from the Home screen; if its runtime is missing, Notisbook
   takes you to the runtime setup.
3. **New notebook** — pick a kernel in the notebook toolbar and write tables to a layer schema. `bronze`, `silver`
   and `gold` already exist in both catalogs; a managed table lands in `s3a://notislake/<layer>/<table>`.

### Command line

| Command / option | Effect |
|---|---|
| `notisbook` | Starts the backend and opens the browser |
| `--port N` | HTTP port on `127.0.0.1` (default `8765`) |
| `--root DIR` | Pins the notebooks folder for this run (the UI cannot change it) |
| `--no-browser` | Does not open the browser |
| `--version` | Prints the installed version |
| `--stop-running` | Stops the instance registered in the data folder and exits |
| `--check-notislake` | Installs the bundled MinIO into a temporary folder, checks it and exits |
| `notisbook update [--version X.Y.Z]` | Updates to the latest (or given) release through the verified installer; downgrades are refused |
| `notisbook uninstall [--yes]` | Removes the software (runtimes, kernels, the Glue container) and keeps your data |

### Update and uninstall

```bash
notisbook update                                   # or run the install command again
notisbook uninstall                                # asks for confirmation; --yes skips it
curl -LsSf https://github.com/ROM-mm/Notisbook/releases/download/v<X.Y.Z>/install.sh | sh   # pin a version
```

Uninstalling keeps your data in `~/.notisbook` (notebooks, lake data, `catalog.db`, preferences), so a reinstall
picks it up again. `NOTISBOOK_HOME` changes the data folder.

### Other ways to install

| Method | Command | Notes |
|---|---|---|
| Install script | `curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh \| sh` | `sh -s -- --version X.Y.Z` (or `NOTISBOOK_VERSION`) pins a release; `sh -s -- --uninstall` removes it. |
| Release assets | [GitHub releases](https://github.com/ROM-mm/Notisbook/releases) | Wheel `notisbook-<version>-py3-none-any.whl`, `constraints-<version>.txt`, the MinIO tarball for `darwin-arm64`, `SHA256SUMS` and `install.sh`. |
| Source (development) | `./start.sh` | Needs `uv`, `node` and `npm`. Builds the frontend when needed and runs the backend with `uv run`. `./start.sh --replace` stops the registered instance first. |

## Who it's for

Data engineers and analysts who want to prototype Spark, Delta, Iceberg, Hudi, DuckDB or AWS Glue code on their own
Mac, and export it to Databricks notebook source, without a cluster or a cloud account.

## Documentation

- [Architecture](docs/ARCHITECTURE.md): components, flows, configuration, data folder layout and security controls.
- [Diagrams](docs/arch/): context, containers, components, deployment and data flow (Mermaid).
- [Architecture decision records](docs/adr/): retrospective records of the choices observed in the code.
- [HTTP API](docs/api/swagger.yaml): OpenAPI 3.0 description of the backend REST routes.

## License

Licensed under [Apache-2.0](LICENSE).

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
