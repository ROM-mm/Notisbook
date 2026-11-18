# Changelog

All notable changes to Notisbook are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-17

First public release of Notisbook: local Spark notebooks for macOS, with versioned Spark environments and a local
lakehouse in one browser UI.

### Added

- **Notebook editor.** Browser UI for `.ipynb` notebooks in a local folder, with Python, Spark SQL and DuckDB SQL
  cells run in Jupyter kernels. The first run seeds the notebooks folder with Delta, Hudi, Iceberg and Glue samples.
- **Versioned Spark environments.** Each Spark version is installed in its own isolated environment (Python 3.12
  via `uv`, `pyspark`, `ipykernel`, `duckdb`) and registered as a kernel. A failed reinstall keeps the previous
  environment.
- **Delta Lake, Apache Iceberg and Apache Hudi.** A bundle matrix per Spark line (3.5 and 4.1) pins the Delta,
  Iceberg, Hudi and Hadoop/S3A jars, each verified by sha256.
- **Automatic JDK selection.** Picks a JDK per Spark line (17 for Spark 3.x; 21 or 17 for Spark 4.x) and writes
  it to the kernelspec.
- **Persistent table catalog.** Tables created by notebooks are registered in a local SQLite catalog and shown in
  the Catalog panel without an open Spark session. Iceberg tables live in a separate `iceberg` catalog.
- **notislake: local MinIO integration.** A local MinIO, started and supervised by Notisbook, serves the
  `notislake` bucket with `bronze`, `silver` and `gold` layers. The schema decides the layer, and a write to the
  wrong layer fails before any data is written. A manual S3 endpoint can be configured instead.
- **AWS Glue 5.0 runtime (Docker).** Optional runtime based on the AWS Glue 5.0 image, with Delta and Iceberg,
  running in a local container. The image is built once from Settings: it downloads the AWS base image and needs
  about 15 GiB of free disk space. The container reaches the catalog only through the backend API.
- **Library management.** Install, upgrade and remove Python libraries in a Spark environment from the UI, with
  `uv pip`.
- **Export.** Notebooks export to `.py` (Databricks notebook source), `.ipynb` and an HTML report without
  JavaScript.
- **Local-only access.** The backend binds to `127.0.0.1` only, with a random token per startup, `Host`/`Origin`
  checks and a strict CSP with sanitized HTML outputs.
- **One-line installer.** `install.sh` verifies the sha256 of every release asset, installs Notisbook with
  `uv tool` and places the bundled MinIO; running it again updates, and `--uninstall` keeps your data.
