<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/favicon-dark.svg">
  <img alt="Notisbook" src="frontend/public/favicon-light.svg" width="96" height="96">
</picture>

# Notisbook

**A local data workstation for notebooks with Spark, DuckDB and AWS Glue on your Mac.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Release](https://img.shields.io/github/v/release/ROM-mm/Notisbook)](https://github.com/ROM-mm/Notisbook/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20Apple%20silicon-lightgrey)](#requirements)

</div>

## Overview

Notisbook runs notebooks on your own machine with everything a lakehouse workflow needs: Apache Spark environments, DuckDB, an AWS Glue 6.0 container, a table catalog for Delta Lake, Apache Iceberg and Apache Hudi, and local S3-compatible storage. It installs as a single command-line tool and opens in your browser.

## The problem it solves

Trying lakehouse code locally usually means assembling a Spark distribution, matching table-format jars to Spark and Scala versions, finding the right JDK, running an object store, configuring a metastore and wiring credentials into every session. Notisbook manages those pieces for you and keeps them consistent across Spark, DuckDB and Glue.

## How it works

- **One local app.** A Python backend serves the web UI and an API on `127.0.0.1`, protected by a token printed at startup.
- **Managed runtimes.** You install Spark versions, DuckDB versions and the AWS Glue 6.0 Docker runtime from the settings page. Each installation is validated before it becomes available.
- **Shared catalog.** Tables created from any runtime are registered in one catalog, so a Delta, Hudi or Iceberg table written in one notebook is visible in the others.
- **Local storage.** A bundled MinIO server, called *notislake*, stores table data in a bucket organized as `landing`, `bronze`, `silver` and `gold`. You can point Notisbook to another S3-compatible store instead.
- **Mixed cells.** A notebook can combine Python, Spark SQL and DuckDB cells, depending on the runtime.

## Benefits

- **Fewer setup steps:** Spark, table-format jars, S3 support and catalog configuration are installed and checked by the app.
- **Version side by side:** several Spark and DuckDB versions can coexist; a failed installation never breaks a working one.
- **Glue compatibility checks:** run notebooks against the AWS Glue 6.0 libraries in a local container, without an AWS account.
- **Your data stays local:** the server listens only on your machine, and notebooks are plain `.ipynb` files.
- **Portable output:** export notebooks as Databricks source (`.py`), `.ipynb` or a self-contained HTML report.

## Use cases

- Prototype Delta Lake, Iceberg or Hudi pipelines before moving them to a cluster.
- Test a PySpark job against a specific Spark version or the AWS Glue 6.0 runtime.
- Query lakehouse tables quickly with DuckDB.
- Learn the medallion layout (`bronze`, `silver`, `gold`) with the bundled sample notebooks.
- Prepare a notebook locally and export it to Databricks.

## Who it is for

Data engineers, analytics engineers and students who work with Spark and lakehouse formats and want a local environment on a Mac with Apple silicon.

## Requirements

- macOS on Apple silicon (native or Rosetta shell).
- A JDK for local Spark: 17 for Spark 3.x; 21 or 17 for Spark 4.x.
- Docker through Colima, only for the AWS Glue runtime (at least 15 GiB free to build the image).
- `uv` is installed automatically by the installer when missing.

## Quick start

Install the latest release:

```bash
curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh | sh
```

Start the app:

```bash
notisbook
```

It prints an address like `http://127.0.0.1:8765/?token=…` and opens it in your browser. On first run, sample notebooks for Spark, Glue and DuckDB are added to your notebooks folder.

## Usage examples

```bash
notisbook --port 9000                 # use another port
notisbook --root ~/projects/notebooks # use a specific notebooks folder
notisbook --no-browser                # do not open the browser
notisbook --stop-running              # stop the running instance
notisbook update                      # update to the latest release
notisbook update --version X.Y.Z      # install a specific release
notisbook uninstall                   # remove the app, keep your data
```

Your data lives in `~/.notisbook` (or `$NOTISBOOK_HOME`) and is kept on uninstall.

To run from a source checkout (requires `uv`, `node` and `npm`):

```bash
./start.sh
```

## More details

- [Architecture](docs/ARCHITECTURE.md) and [diagrams](docs/arch/)
- [Architecture decision records](docs/adr/)
- [HTTP API (OpenAPI)](docs/api/swagger.yaml)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [Code of conduct](CODE_OF_CONDUCT.md)

## License

Notisbook is licensed under the [Apache License 2.0](LICENSE). The MinIO binaries distributed with releases keep their own license (GNU AGPLv3), included in the MinIO package.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
