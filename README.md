<p align="center">
  <img src="docs/assets/banner.png" alt="Notisbook welcome screen — Spark it up locally. Iceberg, Delta, Hudi &amp; Parquet — on your laptop." width="100%">
</p>

# Notisbook

A local notebook interface with a built-in Apache Spark environment manager. Write and run Python, Spark SQL and DuckDB SQL notebooks on your own machine, with Iceberg, Delta, Hudi and Parquet tables — no cluster, no cloud service.

## The Problem It Solves

Trying out Spark and lakehouse table formats locally usually means wiring things up by hand: a PySpark version, a compatible JDK, the Delta/Iceberg/Hudi jars, a metastore and a notebook server. Notisbook bundles all of that into a single application. It installs versioned Spark environments, picks the right JDK for each Spark line, configures the table formats and keeps a persistent catalog of the tables you create.

## How It Works

- A local server (FastAPI) serves the web UI and talks to Jupyter kernels, one per open notebook.
- Each installed Spark version becomes an isolated **environment** (a venv created with `uv`), with PySpark from PyPI, the lakehouse jars downloaded from Maven Central (sha256-verified) and its own kernel.
- Cells can be **Python**, **Spark SQL** (run on the active SparkSession) or **DuckDB SQL** (an in-memory database per kernel).
- The table catalog lives in SQLite (`catalog.db`) and is read by the **Catalog** panel without opening a SparkSession.
- Everything runs on `127.0.0.1`, protected by a token generated on every start.

## Benefits

- Spark 3.x and 4.x environments side by side, installed and removed from the UI itself.
- Iceberg, Delta, Hudi and Parquet ready to use in every environment.
- A table catalog that outlives the Spark session.
- Standard `.ipynb` notebooks, with export to `.ipynb`, `.py` (Databricks format) and self-contained `.html`.

Performance or productivity gains have not been measured: `Not identified in the analyzed code`.

## Use Cases

- Learn and prototype PySpark and Spark SQL transformations before taking them to a cluster.
- Test Delta, Iceberg and Hudi tables locally.
- Compare the behavior of different Spark versions.
- Run quick DuckDB queries alongside Spark code.

## Who It's For

Data engineers and analysts who work with Spark and want a complete local environment. Some features depend on macOS (Homebrew, `/usr/libexec/java_home`, native folder picker).

## Installation

Install with **Homebrew**, from the project tap [`ROM-mm/homebrew-tap`](https://github.com/ROM-mm/homebrew-tap):

```bash
brew tap rom-mm/tap
brew trust rom-mm/tap
brew install notisbook
```

- **`brew trust` is required.** Homebrew refuses formulas from third-party taps without explicit trust and fails with `Refusing to load formula rom-mm/tap/notisbook from untrusted tap rom-mm/tap`. To trust only this formula instead of the whole tap: `brew trust --formula rom-mm/tap/notisbook`.
- The install compiles native dependencies (such as `pyzmq`) and takes a few minutes.
- Homebrew also installs `python@3.12`, `openjdk@17`, `uv`, `zeromq` and `libyaml`. JDK 17 covers Spark 3.x and 4.x; Notisbook finds it on its own, no `JAVA_HOME` needed.

Check the installation:

```bash
notisbook --version
```

Upgrade and uninstall:

```bash
brew upgrade notisbook
brew uninstall notisbook
brew untap rom-mm/tap
```

Uninstalling does not delete the data in `~/.notisbook` (environments, catalog, warehouse and the default notebooks folder `~/.notisbook/notebooks`) or notebooks in any other folder you chose. On the first run, the default notebooks folder starts with three sample notebooks (Delta, Hudi and Iceberg); to remove everything, delete `~/.notisbook` by hand.

## Quick Start

```bash
notisbook
```

This starts the server at `http://127.0.0.1:8765` and opens the browser with the URL that carries the session token. Options:

| option | effect |
|---|---|
| `--port N` | use another port |
| `--root DIR` | set the notebooks folder |
| `--no-browser` | do not open the browser |
| `--version` | print the version |

Once it opens:

1. In **Settings**, under **Spark environments**, install a Spark version.
2. Create a notebook (**New notebook**) and pick the environment in the kernel selector.
3. Run a cell, for example `spark.range(3).show()`.

Common issues:

- **`address already in use`** — another instance is already using port 8765. Stop it or run `notisbook --port 8766`.
- **Another `notisbook` on the PATH** — an active virtualenv with Notisbook installed shadows the Homebrew one. Run `$(brew --prefix)/bin/notisbook` or deactivate the venv.
- **Unauthorized access** — the page was opened without the token. Open the address printed by the server in the terminal (with `?token=…`).

## Usage Examples

Python cell:

```python
df = spark.range(5)
display(df)            # HTML grid, 50 rows by default
display(df, n=200)     # up to 1000 rows
```

Spark SQL cell (uses the active SparkSession):

```sql
SELECT id, id * 2 AS doubled FROM range(5)
```

DuckDB SQL cell (the kernel's in-memory database):

```sql
SELECT 42 AS answer
```

## Development

Requirements: Python 3.12+, `uv`, Node.js and npm, JDK 17 (or 21 for Spark 4.x).

```bash
./start.sh                      # installs frontend deps, builds if needed and starts the backend
cd frontend && npm run dev      # Vite on :5173 with a proxy to the backend on :8765
```

Build the release artifacts (sdist and wheel with the frontend bundled, plus the sha256):

```bash
uv run --project backend python scripts/build_release.py
```

Environment variables: `NOTISBOOK_HOME` (data folder, default `~/.notisbook`), `NOTISBOOK_FRONTEND_DIST`, `NOTISBOOK_PYPI_URL`, `NOTISBOOK_MAVEN_URL`.

## More Details

- [Architecture](docs/ARCHITECTURE.md) (in Portuguese)
- [Architecture decisions (ADRs)](docs/adr/) (in Portuguese)
- [API specification](docs/api/swagger.yaml)

## License

Apache-2.0 — see [LICENSE](LICENSE).
