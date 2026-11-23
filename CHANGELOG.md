# Changelog

All notable changes to Notisbook are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.0] - 2026-11-23

A Home screen that separates the bundled examples from your own notebooks and guides a first run to a runtime, a
cleanup script for build and release leftovers, and a landing page that presents Spark and DuckDB side by side.

### Added

- **Examples row and first-run setup on Home.** The Home screen shows the bundled sample notebooks in their own row,
  with the kernel and runtime each one needs, and keeps them out of "Your notebooks". While no runtime is installed
  it shows a "Get started" block; afterwards it offers "New notebook" and "Runtimes". Opening an example whose
  runtime is missing takes you straight to that runtime's section in Settings › Runtimes.
- **Runtime deep links.** `/settings?runtime=local`, `/settings?runtime=docker` and `/settings?runtime=duckdb` open
  Settings › Runtimes scrolled to that runtime's section and highlight it once the panels above have loaded.
- **Cleanup script.** `python3 scripts/clean.py` lists build and release leftovers with their sizes and asks before
  deleting: frontend builds, lint, type and test caches, `__pycache__`, copied MinIO tarballs and artifacts of
  versions older than the current one. `--deep` adds `node_modules`, `backend/.venv` and a separate question for
  `uv cache clean`, which can be skipped with `--skip-uv`; `--dry-run` only lists and `--yes` skips the question.
  Git-tracked paths and the MinIO source tree in `backend/dist/notislake` are never touched.

### Changed

- **Engine-agnostic landing page.** The landing page presents Spark (local and AWS Glue) and DuckDB side by side,
  with a DuckDB example tab, a new Metadata section mocking the Catalog info, Table info and Notislake panels, and
  colors synced with the app's light and dark themes, in English and Portuguese.
- **Stacked Home rows on small windows.** The examples and setup rows stack vertically on windows up to 640px wide.

### Fixed

- **Side panels when opening a notebook.** Opening a notebook from Home (a sample, a recent notebook or Browse) or
  creating a new one shows the Catalog, Notislake and Notebooks panels with focus mode off.
- **AWS Glue 5.0 install.** The Docker runtime no longer sends a hidden local folder as `connections_dir`, which made
  the Glue 5.0 install fail with "connections_dir: Pasta não encontrada".
- **"Your notebooks" flicker.** The Home cards and the recents list come from a single samples request per root, so
  "Your notebooks" no longer flickers while two requests race.

## [0.7.0] - 2026-11-23

A DuckDB runtime next to Spark, info panels for tables and catalogs in the Catalog, a monochrome theme with
monochrome SVG icons, and an Appearance screen rebuilt on the Runtimes layout.

### Added

- **DuckDB runtime.** Settings › Runtimes has a DuckDB section that installs DuckDB 2.0.1 as a background job, shows
  its status and extensions, and removes it. The extensions (httpfs, iceberg, avro, excel, sqlite_scanner,
  postgres_scanner and spatial) are downloaded once and checked against SHA-256 hashes, so sessions load them
  offline. A DuckDB session starts with an S3 secret for the local object store and the Notislake Iceberg REST
  catalog attached, and the kernel selector shows the runtime with its own icon. A bundled DuckDB sample notebook
  creates `notislake.bronze`, builds an Iceberg table, exports it to Parquet in `s3a://notislake/landing` and reads
  it back with `read_parquet`.
- **Table info panel.** Clicking a table name in the Catalog (or pressing Enter on it) opens a docked panel with
  Overview, Columns, History and Properties. Delta, Parquet and Hudi tables are read from the catalog, Iceberg tables
  from their `metadata.json` with snapshots and stats, and the panel says whether `DROP` deletes the files: managed
  Delta, Parquet and Hudi tables do, Iceberg tables only drop the registration unless `PURGE` is used.
- **Catalog info panel.** Clicking a catalog name opens a panel with Overview, Config and Namespaces, including exact
  namespace and table counts and the local Spark configuration of that catalog. Sensitive keys, values and URI
  credentials are masked by the server.
- **File-format icons in the trees.** The file tree and the Notislake tree show icons for Parquet, Delta, ORC, Avro,
  CSV, PSV, TSV, JSON and TXT files, and both use the same folder icon.
- **Appearance in the shortcut list.** The keyboard shortcut list includes Cmd+, (Ctrl+, elsewhere) for Appearance.

### Changed

- **Monochrome theme.** Light mode is white with black lines and text, and dark mode uses `#2d2d2b`, `#4a4a47` and
  `#f2f1ec`. The green and red status colors and the syntax colors are brighter in both themes while text keeps
  WCAG AA contrast, scrollbars are hidden while scrolling still works, and the active cell has its own background.
- **Monochrome SVG logos.** The runtime selector, Catalog, file tree and Notislake root draw Spark, Iceberg, Hudi,
  S3, Delta, Parquet and Glue as monochrome SVG icons in the text color instead of PNG logos, and the landing page
  uses the same icons.
- **Cell languages follow the kernel.** The cell language menu only offers the languages the active kernel can run,
  labeled Python, Spark SQL and DuckDB, and the HTML report uses the same labels.
- **Panels sized to their content.** The Notebooks panel opens at 256px and widens to fit the longest name, up to
  600px or half the window, until it is resized by hand; a double click on its edge hands sizing back. Table info
  keeps identifiers and paths on one line and widens between 400px and 45% of the window.
- **Appearance screen on the Runtimes layout.** Settings › Appearance now uses the centered Fonts and Preview blocks
  of Runtimes, with font comboboxes grouped into Bundled and System, pending and invalid badges, and Cancel and
  Apply buttons. The ISPF command line is gone, the keyboard shortcuts still work, and Reset to defaults only fills
  the fields until Apply is pressed.
- **Leaner Catalog rows.** Catalog tree rows no longer show the table format and MANAGED/EXTERNAL label, which moved
  to the table info panel.

### Fixed

- **Unavailable cell languages on R and Julia kernels.** Running a cell in a language the kernel does not support
  now returns an error output instead of sending Python code that broke non-Python kernels.
- **Appearance shortcuts.** F1, F3, F4 and Esc only act while focus is inside the Appearance page and F12 is no
  longer intercepted, while F5 and Cmd+S (Ctrl+S elsewhere) always apply instead of reloading the page or opening
  the browser's save dialog.
- **Kernel selector.** The technical kernel name stays visible when two runtimes share a display name, and messages
  about a missing runtime point to Settings › Runtimes.
- **Catalog info after deleting a schema.** The catalog info panel reloads once after a schema is deleted.
- **Notebooks panel on window resize.** The Notebooks panel refits its width when the window is resized and once web
  fonts finish loading.
- **Light theme states.** The active state is distinct from hover in the light theme, and a running Spark job keeps
  its highlighted background.

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
