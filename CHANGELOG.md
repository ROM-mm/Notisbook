# Changelog

All notable changes to Notisbook are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-11-22

A Settings menu with an Appearance screen to pick the interface, code and markdown fonts, and "Runtimes" as the
name for the place where Spark and AWS Glue runtimes are managed.

### Added

- **Settings menu with an Appearance screen.** A new Settings menu, between Run and Help, opens Appearance
  (Cmd+, on macOS, Ctrl+, elsewhere) and Runtimes. The ISPF-style `/settings/appearance` screen chooses the
  Interface, Code cell (and outputs) and Markdown fonts with a live preview, and F5 applies the choice. It is kept
  only in the browser's local storage, under `notisbook.appearance`, and applied before the first render; without
  a saved choice the interface looks exactly as before. Markdown cells being edited use the Markdown font for text
  and the Code font for inline and fenced code.
- **System fonts in the font picker.** On macOS the font list shows the installed font families next to the
  bundled ones, grouped into Bundled and System and each drawn in its own font; a click or F4 opens it. The list
  comes from a new read-only `GET /api/appearance/system-fonts` route, which asks the system once (with a 5-second
  timeout) and caches the result. On other systems, or if the query fails, the picker offers the bundled fonts and
  accepts a typed name. Font names containing backslashes are rejected.

### Changed

- **"Spark environments" is now "Runtimes".** The area that manages Spark and AWS Glue runtimes is called Runtimes
  throughout the interface and is reached from Settings › Runtimes, which is also where backend error messages now
  point. The kernel selector drops its duplicate "Manage environments…" item and hides the technical kernel name,
  showing it as a muted suffix only when two runtimes share the same display name. Routes, URLs and API paths are
  unchanged.

### Fixed

- **Full font names in the font list.** The font list sizes itself to its content within the settings panel, never
  scrolls sideways and shows each name in a tooltip, so long family names are no longer cut mid-word.

## [0.5.0] - 2026-11-20

A retro terminal look in VT323, `echo(df)` for showing DataFrames, a button to clear every output, and a steadier
home screen.

### Added

- **Clear all outputs.** The kernel toolbar has a "Clear all outputs" button that empties the outputs of every code
  cell in one step. Execution counts and each cell's run time and status are kept, and the button is disabled while
  a cell is running or queued.

### Changed

- **`echo(df)` replaces `display(df)` in cells.** DataFrames are now shown with `echo(df)`, which also takes a row
  limit such as `echo(df, n=50)`; `display` is no longer available in cells. The bundled sample notebooks use
  `echo`, and exporting to a Databricks `.py` file turns `echo(...)` back into `display(...)` without the `n=`
  argument, skipping occurrences inside strings and comments.
- **VT323 interface.** The interface uses the VT323 pixel font, scaled to 140% so it stays readable, and the brand
  mark, favicon and panel and focus-mode icons are redrawn as pixel art. Cell code, outputs and code inside markdown
  use VT323 too, without synthesized bold or italic; markdown prose stays in Roboto, now with real 600 and 700
  italics.
- **Landing page as a Data Workstation.** The landing page presents Notisbook as a 1970s-style Data Workstation
  running Spark, with VT323 for the brand, headings and terminal and Monocode for body text.

### Fixed

- **Blank screen in focus mode.** Turning on focus mode while browsing notebooks with no tab open no longer leaves
  an empty screen; it returns to the home screen.
- **Browse from a folder link.** Opening `/tree/<folder>`, directly or through "Browse notebooks…", expands the
  notebook tree down to that folder.
- **Recent notebooks across browser tabs.** Recent notebooks are shared between tabs instead of one tab
  overwriting the other's list, and they stay in memory for the session when the browser blocks local storage.
- **Missing recent notebooks.** Opening a recent notebook that no longer exists removes it from the list and returns
  to the home screen, instead of listing the whole folder first or leaving a broken tab open.

## [0.4.0] - 2026-11-20

A redesigned interface with a single top bar and framed cells, keyboard-driven cell runs, and a public landing page.

### Added

- **Landing page.** A static landing page in English and Portuguese, under `site/`, presents the persistent
  catalog with Spark, Delta, Iceberg and Hudi, the AWS Glue 5.0 Docker runtime and the local notislake (MinIO). It
  ships its fonts and icons locally, loads no external resources and is published to GitHub Pages on every push
  to `main`.
- **Run and advance with Shift+Enter.** Shift+Enter runs a code cell (or renders a markdown one) and moves the
  cursor into the next code cell below, skipping markdown cells and creating a new code cell at the end when there
  is none. Cmd+Enter (Ctrl+Enter on Windows and Linux) runs the cell and keeps the cursor in it.
- **Runtime icon and version in the kernel selector.** The selector shows the Spark or AWS Glue icon with the
  runtime version, such as `3.5.9` for Spark or `5.0` for AWS Glue, and the kernel state as a small square: green
  when idle, gray while busy, red on error. The full state is in the tooltip and the accessible label, and each
  environment in the list shows its icon. Other kernels keep their full display name.

### Changed

- **Single top bar.** The header and the tab bar are merged into one bar: the colored N mark with the wordmark,
  then the open notebooks, each with a small square that is green when active. The File, Edit, View, Run and Help
  menus appear on hover or click of the mark and close with Escape or a click outside. The save state, kernel
  controls (selector, run all, interrupt, restart and "Restart and run all") and panel toggles stay on the right.
- **Reorganized sidebars.** The Notislake card moves to the left sidebar under the Catalog, leaving Notebooks
  alone on the right. Notislake shows the `s3a://` root and always lists `landing`, `bronze`, `silver` and `gold`
  in that order, even before a prefix exists; Catalog schemas follow the same order and show per-format table
  icons. Machine usage moves to the shortcut bar at the bottom.
- **Framed cells.** Each cell has a thin border that strengthens on the active cell, a header with the language
  on the left and the run status, interrupt and cell menu on the right, and a dashed rule before the output. Line
  numbers, the header run button and the blue edge on the cell being edited are gone, and the notebook scrollbar
  is hidden while scrolling still works by wheel, trackpad and keyboard.
- **Blue accent and colored syntax.** The accent color is now blue, syntax highlighting is colored in both dark
  themes, and the add-cell bar is always visible, with a small green square in its "code" and "markdown" buttons.

### Fixed

- **Stale run status after a language change.** A cell's run status is cleared when its language changes.

## [0.3.0] - 2026-11-19

Quieter cell output: Spark keeps its log noise to itself, and package downloads show up as a short list.

### Added

- **Spark package summary.** When a notebook sets `spark.jars.packages` (for example with
  `configure_spark_with_delta_pip`), the cell no longer shows the whole Ivy resolution log. It shows one block,
  "📦 Pacotes Spark", with one line per resolved package, such as `io.delta:delta-spark_2.12:3.3.3`, and where it
  came from (`central` or the local cache). If a package cannot be resolved, the full log is shown together with
  the error.

### Changed

- **Only errors, prints and results in cell output.** Spark `WARN` and `INFO` log lines, such as plan truncation
  warnings, no longer appear under the cells; Spark `ERROR` lines still do. The "Setting default log level"
  message at session start is gone in the local runtime. To see warnings again in a session, run
  `spark.sparkContext.setLogLevel("WARN")`; the level you set is kept for the rest of the session.
- **Requirements before installation.** The README lists the system requirements before Quick start, including
  the AWS Glue 5.0 base image (`public.ecr.aws/glue/aws-glue-libs:5`, pinned by digest) to pull before using the
  Docker runtime.

## [0.2.0] - 2026-11-19

A cleaner start screen with your recent notebooks, and sample notebooks that show the notislake lakehouse layout.

### Added

- **Recent notebooks on the start screen.** With no tab open, Notisbook shows only the brand, "New notebook" and
  the five most recently opened notebooks, each with its full path on disk. Recents are kept per notebooks folder,
  drop files that no longer exist and follow renames and deletes made in the file browser. A "Browse notebooks…"
  link opens the Notebooks panel.

### Changed

- **Start screen without the app chrome.** The full interface appears once a notebook is open; with tabs open, the
  start screen is shown inside it so your notebooks stay visible. The "Open notebooks" button was removed.
- **New brand mark and tagline.** The start screen shows the app icon in color, the "notisbook" wordmark and the
  tagline "Process anything. Locally.", which also replaces "Spark it up locally." in the header.
- **Sample notebooks write external tables to notislake.** The Delta, Hudi, Iceberg and Glue samples now register
  only external tables in the `bronze` schema, with their files in `s3a://notislake/bronze/<table>_files`, and can
  be run again without errors. The Glue sample was reduced to a single Delta table, in the same format as the
  others. Samples are copied only on the first run, so existing installations keep their current notebooks.

### Fixed

- **Sample notebooks on a fresh install.** The samples no longer query tables they do not create, so every cell
  runs on a new installation.

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
