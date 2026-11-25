# Changelog

All notable changes to Notisbook are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.2] - 2026-11-24

A security release: local Spark kernels stop listening on the local network.

### Fixed

- **Local Spark kernels bound to loopback.** The Spark driver and its Web UI used to listen on all network
  interfaces, so anyone on the same network could reach the SQL tab, the query plans and the job controls of a
  running notebook. Every local Spark runtime now sets `spark.driver.bindAddress` and `spark.driver.host` to
  `127.0.0.1` and starts the kernel with `SPARK_LOCAL_IP=127.0.0.1`, which is what the Web UI actually follows. The
  Web UI still opens on the Mac itself, without the buttons that kill jobs and stages. Existing runtimes keep the old
  settings: reinstall each local Spark runtime in Settings › Runtimes to apply the fix. The AWS Glue runtime is not
  covered by this change.

### Changed

- **Architecture guide.** `docs/ARCHITECTURE.md` and the five diagrams in `docs/arch/` were regenerated from the
  current code and now describe the loopback binding of local Spark kernels. The guide is now written in Portuguese.

## [0.13.1] - 2026-11-24

A documentation release: the project documentation is rewritten from the current code, with no change to the app.

### Added

- **Architecture guide.** `docs/ARCHITECTURE.md` describes how Notisbook works today: the single local process on
  `127.0.0.1`, the Spark, DuckDB and AWS Glue 6.0 runtimes, the SQLite catalog, the local MinIO storage, the security
  controls and the release pipeline, each point pointing to the source file it comes from.
- **Diagrams.** Five Mermaid diagrams in `docs/arch/`: system context, containers, backend components, deployment on
  the Mac and the path of a cell execution.
- **HTTP API reference.** `docs/api/swagger.yaml` is an OpenAPI 3.0 description of the backend API, including the
  three WebSocket endpoints and the three kinds of token (UI, runtime and shutdown).
- **Decision records.** 26 architecture decision records in `docs/adr/`, from the WebSocket protocol to the Apple
  silicon–only support. Where the code does not show why a choice was made, the record says so.

### Changed

- **README.** Rewritten around what Notisbook does, who it is for, the requirements and a quick start, now citing
  AWS Glue 6.0.

## [0.13.0] - 2026-11-24

The AWS Glue runtime moves to Glue 6.0 (Spark 4.1, Scala 2.13, Python 3.13), and only the latest Glue version is
offered from now on, because each image takes more than 10 GB.

### Changed

- **AWS Glue 6.0.** The Docker runtime is built on `public.ecr.aws/glue/aws-glue-libs:6.0`, pinned by digest: Spark
  4.1.1, Scala 2.13, Python 3.13, Delta 4.2.0, Iceberg 1.11.0 and Hudi 1.1.1. Delta, Iceberg and Hudi keep working in
  SQL and DataFrames, with Spark 4's default ANSI mode, as in AWS Glue itself.
- **Only the latest Glue version.** Glue 5.0 was removed from Settings › Runtimes; there is a single AWS Glue
  runtime.
- **Version-free names.** The runtime, its container and its kernel are now `glue`, `notisbook-glue` and
  `notisbook-docker-glue`; the version shows only in the label ("AWS Glue 6.0"), so future Glue upgrades no longer
  break saved notebooks. Notebooks saved with the Glue 5.0 kernel ask for a kernel once: pick "AWS Glue 6.0".
- **Glue examples.** `glue/delta`, `glue/hudi` and `glue/iceberg` open on the new kernel.

### Removed

- **Glue 5.0 leftovers, automatically.** On startup, Notisbook removes the kernel, container and `notisbook/*` image
  of runtimes that left the catalog, such as Glue 5.0. Only items marked as Notisbook's are touched, and a failure
  never stops the app from starting. The AWS base image `public.ecr.aws/glue/aws-glue-libs:5` (about 12 GB) is not
  Notisbook's and stays: remove it with `docker rmi public.ecr.aws/glue/aws-glue-libs:5`. If you had already removed
  the Glue 5.0 runtime, also run `docker image rm notisbook/glue:5.0`.

### Fixed

- **Clear error without Delta.** If the Delta jar is missing from the Glue image, the kernel stops with a clear error
  instead of starting a session without Delta.

## [0.12.0] - 2026-11-24

DuckDB now has managed versions with their own libraries, like Spark; kernels live inside the Notisbook data folder;
Spark jars are downloaded once and shared; and the example notebooks are organized by runtime.

### Added

- **Managed DuckDB versions.** Several DuckDB versions can be installed side by side (2.0.1 and 1.5.6 are in the
  catalog), each with its own kernel (`duckdb-<major>-<minor>-<patch>`). Installing or removing one leaves the others
  untouched.
- **Libraries per DuckDB version.** Each DuckDB version has its own PyPI libraries (add, upgrade, uninstall), with the
  same rules as Spark; `duckdb` and `ipykernel` are protected.
- **Shared jar cache.** Spark jars are stored once in `~/.notisbook/jars/<sha256>/` and referenced by every
  environment, so installing another Spark version no longer downloads the AWS SDK again. Each jar is checked against
  its sha256, and jars no environment uses anymore are removed automatically.
- **S3A for every Spark version.** The S3A jars now follow the Hadoop shipped inside pyspark, so Spark versions without
  a Delta/Iceberg/Hudi bundle install and open sessions with S3A, without the table formats.
- **One install picker in Settings › Runtimes.** A single combo groups Spark (Data processing), DuckDB (Analytics) and
  Docker (AWS Glue), shows what is installed or installing, labels the supported table formats and works from the
  keyboard.
- **Grouped kernel selector.** Kernels are grouped by runtime: Spark, DuckDB, Docker and Other.
- **Examples by runtime.** New `spark/` and `glue/` notebooks for Delta, Hudi and Iceberg, plus `duckdb/duckdb.ipynb`.
  The Home lists `spark/delta`, `duckdb/duckdb` and `glue/iceberg`.

### Changed

- **Kernels live in the data folder.** Kernelspecs are written to `~/.notisbook/kernels` (or `$NOTISBOOK_HOME/kernels`)
  instead of the global Jupyter folder. On startup, Notisbook moves its own kernels from the global folder, and removes
  kernels whose environment no longer exists.
- **Only Notisbook kernels are listed.** Jupyter kernels installed outside Notisbook no longer appear in the app and
  cannot be started from it. Notisbook kernels also no longer appear in other Jupyter tools.
- **DuckDB API by version.** The `/api/duckdb` routes now take a version: `POST /versions`, `DELETE /versions/{v}`,
  `GET /versions/{v}/extensions`, and `GET`/`POST /versions/{v}/packages` with `/upgrade` and `/uninstall`.
  `GET /api/duckdb` returns lists for `installed` and `installing`, plus the `catalog`.
- **Spark catalog.** The catalog offers the latest patch of 3.5 and of each 4.x line; lines before 3.5 are no longer
  offered.
- **Settings › Runtimes.** A single Installed list covers Spark, DuckDB and Docker, and "Reload catalog" refreshes the
  three. The separate DuckDB section was removed.
- **`notisbook uninstall`** also removes `~/.notisbook/kernels`, `~/.notisbook/jars` and this data folder's kernels
  left in the global Jupyter folder.
- **Busy DuckDB versions.** Opening a session is refused while that DuckDB version is being installed or its libraries
  are changing.

### Removed

- **Old DuckDB routes.** `GET /api/duckdb/extensions`, `POST /api/duckdb/install` and `DELETE /api/duckdb` were
  replaced by the versioned routes above.
- **Old loose examples.** `delta.ipynb`, `glue.ipynb`, `hudi.ipynb` and `iceberg.ipynb` were replaced by the
  per-runtime notebooks.

### Fixed

- **Spark install check.** The install smoke test no longer fails when the Spark progress bar shares a line with the
  success marker.
- **Missing runtimes.** Opening a notebook whose kernel was removed now returns `runtime_not_installed`, pointing to
  Settings › Runtimes, and notebooks saved with the `duckdb` kernel open on the newest installed DuckDB version.
- **Orphan kernels on uninstall.** `notisbook uninstall` also removes kernels whose environment was already gone.
- **Docker hint.** The message for a missing Docker container points to "Recreate" in Settings › Runtimes.

## [0.11.0] - 2026-11-24

The AWS Glue runtime now reads and writes Apache Hudi tables, its cell output is no longer flooded by Spark logs, and
the Catalog tree is lighter: tables are leaves and their columns live in the Table info panel.

### Added

- **Hudi in the AWS Glue runtime.** The Glue Spark session loads the Hudi extension
  (`HoodieSparkSessionExtension`) with the Kryo serializer Hudi requires, in the same order as the local Spark
  runtime, and the catalog registry and layer check accept Hudi tables created in the Docker runtime.
- **Iceberg and Hudi class check in the Glue container.** Validating the Glue runtime now confirms that the Iceberg
  and Hudi classes actually load inside the container, so a broken image is reported before the first notebook runs.
- **Hudi tables in the Glue example.** `glue.ipynb` creates a managed and an external Hudi table; the load into the
  external table uses `MERGE INTO`, so running the whole notebook twice finishes without errors.
- **Community files.** The repository now has a contributing guide (`CONTRIBUTING.md`), a pull request template, a
  code of conduct (`CODE_OF_CONDUCT.md`) and a security policy (`SECURITY.md`).

### Changed

- **Tables are leaves in the Catalog tree.** Expanding a table no longer lists its columns; a click or Enter opens
  Table info, whose Columns tab shows them. The `GET /api/catalog/columns` route was removed (it served only the
  tree); Table info keeps using `GET /api/catalog/table`.
- **Layers always visible on `spark` and `hudi`.** Both catalog nodes always show `bronze`, `silver` and `gold`, and
  an empty `default` schema is hidden.
- **`tornado` 6.6.1.** The backend dependency was bumped from 6.6 to 6.6.1.

### Fixed

- **Quiet Spark output in the Glue runtime.** The Spark driver now logs only errors, through a log4j2 configuration
  added after any existing `SPARK_SUBMIT_OPTS`, and the kernel relay drops SLF4J lines and JOL warnings, matching the
  local Spark runtime.
- **No "0 rows" on load cells.** The load cells of `glue.ipynb` no longer print an empty "0 rows" result.
- **`landing/` prefix in Notislake.** The MinIO bootstrap now creates `landing/` alongside `bronze/`, `silver/` and
  `gold/`.
- **Exact names in the Catalog.** Layer and `default` names are compared with their exact spelling when the tree
  labels schemas, while the check for an existing `default` schema ignores letter case.

## [0.10.0] - 2026-11-23

Notisbook can now update and uninstall itself from the command line, and a release can be rehearsed on your own Mac
before it is published.

### Added

- **`notisbook update`.** Installs the latest release, or a specific one with `notisbook update --version X.Y.Z`,
  through the release's own `install.sh`. It says "already up to date" when there is nothing newer, refuses to go back
  to an older version so `catalog.db` is never opened by a version that predates it, and only runs `install.sh` when
  its checksum is listed in the release's `SHA256SUMS`.
- **`notisbook uninstall`.** Lists what will be removed and what will be kept, with sizes, and asks
  `Proceed with the uninstall? [y/N]` (only `y` or `yes` confirms; `--yes` skips the question). It removes the app, the bundled MinIO package, the Spark and
  DuckDB environments, the Jupyter kernels and the AWS Glue container of this data folder, and keeps your data:
  the Notislake lake (`minio/data`), its credentials, `catalog.db`, the warehouse folders, your notebooks and your
  preferences, so a later reinstall picks up where you left off. Docker images are left in place.
- **Local release rehearsal.** `./scripts/release.sh --local-install X.Y.Z` runs the same checks as `--dry-run`,
  builds version X.Y.Z and installs it on this Mac from `backend/dist/local-X.Y.Z/`, without committing, tagging,
  pushing or creating a GitHub release. It reuses the MinIO tarball already built (or the one from the latest
  release) and only compiles MinIO when neither is available.

### Changed

- **`install.sh --uninstall` does the full cleanup.** On installs that ship `notisbook uninstall`, the installer hands
  the removal over to it; older installs fall back to the previous behaviour and warn that environments, kernels and
  the container were left behind.
- **`install.sh` is checksummed.** Every release now lists `install.sh` in `SHA256SUMS`, and `release.sh` checks that
  the listed checksum matches the script before publishing.

### Fixed

- **`--port` is refused with `update` and `uninstall`.** Any explicit `--port`, including the default value, is now
  rejected when combined with a subcommand instead of being silently ignored.
- **`notisbook update` reports disk errors.** A `SHA256SUMS` or `install.sh` that cannot be read, or a temporary
  folder that cannot be created, now ends the update with a short error message instead of a Python traceback.
- **Data folder comparison respects case.** `notisbook uninstall` compares data folder paths by identity
  (`os.path.samefile`) instead of lowercasing them, so two folders that differ only in case are not mistaken for
  each other on a case-sensitive volume.
- **Clearer Intel Mac message.** `install.sh` now stops on an Intel Mac with "Notisbook supports Apple silicon only
  (detected x86_64)".
- **Sturdier `/clean` script.** `scripts/clean.py` no longer hangs on a slow `uv cache dir` or uv cache measurement
  (both now time out), keeps the bundled MinIO tarballs in `backend/dist` when `backend/dist/notislake` is missing,
  matches protected paths regardless of letter case, and shows the uv cache size as "≥ X" when part of it cannot be
  read. The list of what it removes is unchanged.

## [0.9.0] - 2026-11-23

Notisbook now supports Apple silicon Macs only: releases ship a single arm64 build of the bundled object store and
Intel Macs are refused at install time.

### Changed

- **Apple silicon only (breaking).** Releases no longer build or publish the Intel (`darwin-amd64`) MinIO tarball,
  the wheel gate only checks `aarch64-apple-darwin`, and the DuckDB runtime only downloads `osx_arm64` extensions.
  `install.sh` stops on an Intel Mac with "Notisbook supports Apple silicon only" before installing `uv`. Intel Macs
  are no longer supported.
- **Rosetta keeps working.** A Python process running under Rosetta on an Apple silicon Mac is detected through
  `sysctl.proc_translated` and still uses the arm64 MinIO binaries and DuckDB extensions, so existing installs that
  run an x86_64 Python keep starting.

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
