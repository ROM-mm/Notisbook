<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/favicon-dark.svg">
  <img alt="Notisbook" src="frontend/public/favicon-light.svg" width="96" height="96">
</picture>

# Notisbook — Process anything. Locally.

Edit `.ipynb` notebooks and run Python, Spark SQL and DuckDB SQL cells in Jupyter kernels. Notisbook installs
Spark environments with Delta Lake, Apache Iceberg and Apache Hudi jars verified by sha256, keeps a persistent
table catalog in SQLite and runs a local MinIO bucket organized in `bronze`, `silver` and `gold` layers. Everything
runs on your machine: the backend listens on `127.0.0.1` only.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Release](https://img.shields.io/github/v/release/ROM-mm/Notisbook)](https://github.com/ROM-mm/Notisbook/releases)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](#requirements)

[Releases](https://github.com/ROM-mm/Notisbook/releases) • [Architecture](docs/ARCHITECTURE.md) • [ADRs](docs/adr/) • [HTTP API](docs/api/swagger.yaml)

</div>

---

## Requirements

Make sure your Mac meets these requirements **before** installing Notisbook.

- macOS on Apple silicon or Intel (the installer refuses other systems).
- `curl` (or `wget`), `awk` and `shasum` for the installer.
- `uv` 0.8.4 or newer; if it is missing, the installer installs `uv` 0.10.8.
- To create Spark environments: JDK 17 for Spark 3.x; JDK 21 (or 17) for Spark 4.x.

### Optional: AWS Glue Docker runtime

Only needed if you want to run notebooks on the AWS Glue runtime (Glue 5.0: Spark 3.5, Python 3.11, Java 17).

- Docker (for example via Colima), with about 15 GiB of free disk space for the image build.
- The AWS Glue base image, pulled with Docker and kept locally:

  ```bash
  docker pull public.ecr.aws/glue/aws-glue-libs:5@sha256:a54bd25fb72c55a2f28d07656a3cda943a042f345cc25f4c2c170667be864f01
  ```

  This is the exact image Notisbook builds its Glue runtime on (pinned by digest in
  `backend/src/notisbook/runtimes/glue/Dockerfile`). Keep it: removing it forces the next runtime build to
  download it again.

## Quick start

```bash
curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh | sh
notisbook
```

The installer downloads the release's `SHA256SUMS` and checks the sha256 of the Notisbook wheel, the
*constraints* file and the MinIO tarball for your architecture before installing anything. It stops a running
Notisbook, installs the wheel with `uv tool install --no-build` on Python 3.12 (installing `uv` first if it is
missing) and places the MinIO package (the **notislake**) in `~/.local/share/notisbook/notislake`. To update, run
the same command again. `--uninstall` removes Notisbook and keeps your data in `~/.notisbook`. The `notisbook`
command lives in the `uv tool` bin directory (usually `~/.local/bin`); if it is not on your `PATH`, the installer
tells you how to add it.

`notisbook` starts the backend on `http://127.0.0.1:8765`, prints the address with a per-startup token
(`/?token=<token>`) and opens your default browser. On the first run, the default notebooks folder
(`~/.notisbook/notebooks`) is seeded with the samples `delta.ipynb`, `hudi.ipynb`, `iceberg.ipynb` and `glue.ipynb`.

| Option | Effect |
|---|---|
| `--port N` | HTTP port on `127.0.0.1` (default `8765`) |
| `--root DIR` | Pins the notebooks folder for this run (the UI cannot change it) |
| `--no-browser` | Does not open the browser |
| `--version` | Prints the installed version |
| `--stop-running` | Stops the instance registered in the data folder and exits |
| `--check-notislake` | Installs the bundled MinIO into a temporary folder, checks it and exits |

## What's in the box

| Capability | What it means |
|---|---|
| **Notebook editor** | Browser UI for `.ipynb` files in a local folder, with Python, Spark SQL and DuckDB SQL cells run in Jupyter kernels. |
| **Spark environments** | Each Spark version is installed in its own isolated, versioned environment (Python 3.12 via `uv`, `pyspark`, `ipykernel`, `duckdb`) and registered as a kernel. A failed reinstall keeps the previous environment. |
| **Lakehouse formats** | A static bundle matrix per Spark line (3.5 and 4.1) pins Delta Lake, Iceberg, Hudi and Hadoop/S3A jars, each checked by sha256. |
| **JDK selection** | Picks a JDK per Spark line (17 for Spark 3.x; 21 or 17 for Spark 4.x) and writes it to the kernelspec. |
| **Persistent catalog** | Tables created by notebooks are registered in a local SQLite file (`catalog.db`), shown in the data panel without an open Spark session. Iceberg lives in a separate `iceberg` catalog. |
| **notislake** | A local MinIO, started and supervised by Notisbook, serves the `notislake` bucket with `bronze`, `silver` and `gold` layers. A manual S3 endpoint can be configured instead. |
| **Docker runtime** | Optional runtime based on the AWS Glue 5.0 image (Delta and Iceberg) in a local container, which reaches the catalog only through the backend API. |
| **Library management** | Install, upgrade and remove Python libraries in a Spark environment from the UI, with `uv pip`. |
| **Export** | Notebooks export to `.py` (Databricks *notebook source*), `.ipynb` and an HTML report without JavaScript. |
| **Local-only access** | Fixed `127.0.0.1` bind, a random token per startup, `Host`/`Origin` checks and a strict CSP with sanitized HTML outputs. |

### Other ways to install

| Method | Command | Notes |
|---|---|---|
| Install script | `curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh \| sh` | macOS, Apple silicon and Intel. `sh -s -- --version X.Y.Z` (or `NOTISBOOK_VERSION`) pins a release; `sh -s -- --uninstall` removes it. |
| Release assets | [GitHub releases](https://github.com/ROM-mm/Notisbook/releases) | Wheel `notisbook-<version>-py3-none-any.whl`, `constraints-<version>.txt`, MinIO tarballs per architecture, `SHA256SUMS` and `install.sh`. |
| Source (development) | `./start.sh` | Needs `uv`, `node` and `npm`. Installs frontend dependencies when needed, rebuilds the frontend if it changed and runs the backend with `uv run`. `./start.sh --replace` stops the registered instance first. |

## Documentation

- [Architecture](docs/ARCHITECTURE.md): components, flows, configuration, data folder layout and security controls.
- [Diagrams](docs/arch/): context, containers, components, deployment and data flow (Mermaid).
- [Architecture decision records](docs/adr/): retrospective records of the choices observed in the code.
- [HTTP API](docs/api/swagger.yaml): OpenAPI 3.0 description of the backend REST routes.

## Contributing

Run from source with the repository scripts:

```bash
./start.sh                      # build the frontend if needed and start the backend with uv run
./start.sh --replace            # stop the registered instance first
./start.sh --port 8800 --no-browser
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Releases are produced by `scripts/release.sh <X.Y.Z>`; `scripts/release.sh --dry-run <X.Y.Z>` runs only the checks
and prints the commands without publishing.

Licensed under [Apache-2.0](LICENSE).

---

**Author:** Romerito Morais

**Version:** 20261117074712

**Date:** 2026-11-17 07:47:12

**SKILL:** Document
