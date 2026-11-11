"""Spark SQL / DuckDB SQL cells and shared result renderer for the user's kernel.

The renderer lives in a hidden module (`_notisbook_display`) installed into the
kernel by an idempotent `ensure` snippet, so nothing leaks into the user's
namespace. It builds the `display_data` bundle (HTML table + ASCII `text/plain`
fallback, capped in rows and cell length) and registers a lazy IPython
`text/html` formatter for PySpark DataFrames.

Row limits: SQL/DuckDB cells and a bare `df` as the last line show up to
`MAX_ROWS`; inside `display(df)` the limit is `DISPLAY_ROWS`, adjustable with
the keyword `display(df, n=...)` (1..`MAX_ROWS`). That works through a marked
wrapper of `display` (builtins, `IPython.display`, `IPython.core.display_functions`)
that hands `n` to the formatter via a ContextVar; the original stays reachable
through `_notisbook_original`.

The SQL query travels as a JSON string literal decoded inside the kernel, so its
text is never spliced into code. `getOrCreate` is never called: with no active
SparkSession the Spark cell fails with a clear message instead of starting a JVM.

DuckDB cells need no SparkSession: one lazy in-memory connection per kernel is
kept in the module's `STATE` (carried over when the module version changes) and
dies with the kernel. Extension autoinstall is off so the kernel stays offline.
"""

import hashlib
import json

RENDERER_MISSING_MESSAGE = "Notisbook renderer is not installed in the kernel; restart the kernel"
NO_SESSION_MESSAGE = "No active SparkSession; create one in a Python cell"
DUCKDB_MISSING_MESSAGE = (
    "DuckDB is not installed in this Spark environment; reinstall it from the Spark versions panel"
)
MAX_ROWS = 1000
DISPLAY_ROWS = 50
MAX_CELL_CHARS = 500
MODULE_NAME = "_notisbook_display"

# Plain string (not an f-string) so CSS/dict braces stay literal; the __TOKENS__
# are substituted in `_KERNEL_SOURCE`. Executed as the body of the hidden module,
# so it must not import IPython or pyspark at the top (kernels may lack either).
_KERNEL_TEMPLATE = r'''
import contextvars, html, json, operator, sys

MAX_ROWS = __MAX_ROWS__
DISPLAY_ROWS = __DISPLAY_ROWS__
MAX_CELL_CHARS = __MAX_CELL_CHARS__
# Spark simpleString names + DuckDB type names (compared in lowercase).
NUMERIC_TYPES = {
    "tinyint", "smallint", "int", "bigint", "float", "double", "decimal",
    "integer", "hugeint", "utinyint", "usmallint", "uinteger", "ubigint", "uhugeint", "real",
}
# Statements whose DuckDB result is only a status/count column: shown as "OK".
DUCKDB_STATUS_STATEMENTS = {
    "CREATE", "DROP", "ALTER", "SET", "ATTACH", "DETACH", "TRANSACTION", "INSERT",
    "UPDATE", "DELETE", "LOAD", "EXTENSION", "VACUUM", "ANALYZE", "MERGE_INTO",
    "COPY_DATABASE", "EXPORT",
}
STATE = {}
STYLE = (
    "<style>"
    ".nb-grid th, .nb-grid td { text-align: left; }"
    ".nb-grid th.num, .nb-grid td.num { text-align: right; }"
    ".nb-grid thead th { border-bottom: 1px solid var(--color-border-strong); }"
    ".nb-grid .null { color: #8a8f98; font-style: italic; }"
    ".nb-grid-footer { padding: 6px 10px; font-size: 12px; opacity: 0.7; }"
    "</style>"
)

def clip(value):
    if value is None:
        return None
    return value if len(value) <= MAX_CELL_CHARS else value[:MAX_CELL_CHARS] + "…"

def is_numeric(type_name):
    return type_name.split("(")[0].strip().lower() in NUMERIC_TYPES

def limit_var():
    # Lives in STATE so wrappers from older module versions share the same var.
    return STATE.setdefault("limit_var", contextvars.ContextVar("notisbook_limit", default=None))

def footer_text(count, truncated, limit):
    if truncated:
        text = "showing the first %d rows" % limit
        # Hint only inside display(): there `n` can actually raise the limit.
        return text + " \u2014 use display(df, n=...)" if limit_var().get() is not None else text
    return "1 row" if count == 1 else "%d rows" % count

def html_table(names, numeric, rows, footer):
    head = "".join(
        '<th class="%s">%s</th>' % ("num" if n else "", html.escape(name))
        for name, n in zip(names, numeric)
    )
    body = []
    for row in rows:
        cells = []
        for value, n in zip(row, numeric):
            text = '<span class="null">null</span>' if value is None else html.escape(value)
            cells.append('<td class="%s">%s</td>' % ("num" if n else "", text))
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        STYLE + '<div class="nb-grid"><table><thead><tr>' + head + "</tr></thead><tbody>"
        + "".join(body) + "</tbody></table>"
        + '<div class="nb-grid-footer">' + html.escape(footer) + "</div></div>"
    )

def plain_table(names, rows, footer):
    flat = [["null" if v is None else v.replace("\n", " ") for v in row] for row in rows]
    widths = [len(name) for name in names]
    for row in flat:
        widths = [max(w, len(v)) for w, v in zip(widths, row)]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    def line(values):
        return "| " + " | ".join(v.ljust(w) for v, w in zip(values, widths)) + " |"
    lines = [sep, line(names), sep] + [line(row) for row in flat] + [sep, footer]
    return "\n".join(lines)

def _build(df, limit):
    fields = df.schema.fields
    names = [f.name for f in fields]
    numeric = [is_numeric(f.dataType.simpleString()) for f in fields]
    # Positional rename + CAST: duplicate column names and non-string types
    # (dates, decimals) would otherwise break selection/serialization. substring
    # caps each value in Spark so the driver never collects the full text; one
    # extra char lets `clip` tell "exactly MAX" from "longer" and add the ellipsis.
    safe = df.toDF(*["c%d" % i for i in range(len(names))])
    cast = safe.selectExpr(*[
        "substring(CAST(c%d AS STRING), 1, %d) AS c%d" % (i, MAX_CELL_CHARS + 1, i)
        for i in range(len(names))
    ])
    collected = cast.limit(limit + 1).collect()
    truncated = len(collected) > limit
    rows = [[clip(v) for v in r] for r in collected[:limit]]
    footer = footer_text(len(rows), truncated, limit)
    return {
        "text/html": html_table(names, numeric, rows, footer),
        "text/plain": plain_table(names, rows, footer),
    }

def _build_duckdb(rel):
    names = list(rel.columns)
    numeric = [is_numeric(str(t)) for t in rel.types]
    # Positional refs (#n) tolerate duplicate column names; CAST + substring cap each
    # value in the engine (one extra char lets `clip` add the ellipsis), and the limit
    # keeps the full result out of Python.
    proj = ", ".join(
        "substring(CAST(#%d AS VARCHAR), 1, %d) AS c%d" % (i + 1, MAX_CELL_CHARS + 1, i)
        for i in range(len(names))
    )
    collected = rel.project(proj).limit(MAX_ROWS + 1).fetchall()
    truncated = len(collected) > MAX_ROWS
    rows = [[clip(v) for v in r] for r in collected[:MAX_ROWS]]
    footer = footer_text(len(rows), truncated, MAX_ROWS)
    return {
        "text/html": html_table(names, numeric, rows, footer),
        "text/plain": plain_table(names, rows, footer),
    }

def _duckdb_connection(ext_dir):
    con = STATE.get("duckdb")
    if con is not None:
        return con
    try:
        import duckdb
    except ImportError:
        raise RuntimeError(__DUCKDB_MISSING__) from None
    import os
    os.makedirs(ext_dir, exist_ok=True)
    con = duckdb.connect(":memory:", config={
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": True,
        "extension_directory": ext_dir,
    })
    STATE["duckdb"] = con
    return con

def run_duckdb(payload, ext_dir):
    display = original_display()
    con = _duckdb_connection(json.loads(ext_dir))
    sql = json.loads(payload)
    stmts = con.extract_statements(sql)
    if not stmts:  # comment-only or blank cell
        display({"text/plain": "OK"}, raw=True)
        return
    kind = stmts[-1].type.name
    rel = con.sql(sql)
    if rel is None or kind in DUCKDB_STATUS_STATEMENTS:
        display({"text/plain": "OK"}, raw=True)
    else:
        display(_build_duckdb(rel), raw=True)

def unwrap(func):
    while hasattr(func, "_notisbook_original"):
        func = func._notisbook_original
    return func

def original_display():
    # Sem depender de `display_functions`: a importação pode falhar em outras versões.
    try:
        import IPython.display
        return unwrap(IPython.display.display)
    except Exception:
        from IPython.core import display_functions
        return unwrap(display_functions.display)

def check_n(n):
    if n is None:
        return DISPLAY_ROWS
    message = "n must be an integer between 1 and %d" % MAX_ROWS
    if isinstance(n, bool):
        raise TypeError(message)
    try:
        value = operator.index(n)
    except TypeError:
        raise TypeError(message) from None
    if not 1 <= value <= MAX_ROWS:
        raise ValueError(message)
    return value

def wrap_display(original):
    def display(*objs, n=None, **kwargs):
        limit = check_n(n)  # before any output
        var = limit_var()
        token = var.set(limit)
        try:
            return original(*objs, **kwargs)
        finally:
            var.reset(token)
    display._notisbook_original = original
    return display

def render(df, limit):
    # None means "fall back to the default repr": streaming frames cannot be
    # collected, and a failure here must not break the display machinery.
    try:
        if getattr(df, "isStreaming", False):
            return None
        return _build(df, limit)
    except Exception:
        return None

def html_formatter(df):
    limit = limit_var().get()
    # Outside display() (displayhook of a bare `df`) keeps the MAX_ROWS cap.
    bundle = render(df, MAX_ROWS if limit is None else limit)
    return None if bundle is None else bundle["text/html"]

def install_display():
    import builtins
    import IPython.display
    from IPython.core import display_functions
    # Always rewrap the true original so versions never stack wrappers.
    wrapper = wrap_display(unwrap(display_functions.display))
    display_functions.display = wrapper
    IPython.display.display = wrapper
    if hasattr(builtins, "display"):
        builtins.display = wrapper

def register():
    from IPython import get_ipython
    ip = get_ipython()
    if ip is None:
        return
    formatter = ip.display_formatter.formatters["text/html"]
    for module in ("pyspark.sql.dataframe", "pyspark.sql.connect.dataframe"):
        loaded = sys.modules.get(module)
        cls = getattr(loaded, "DataFrame", None)
        if cls is not None:
            # Already imported: IPython may have moved an earlier by-name printer
            # into `type_printers`, so only a direct for_type replaces it.
            formatter.for_type(cls, html_formatter)
        else:
            formatter.for_type_by_name(module, "DataFrame", html_formatter)
    # Por último: uma falha do wrapper não pode derrubar a grade já registrada.
    try:
        install_display()
    except Exception:
        pass

def run(payload):
    display = original_display()
    mod = sys.modules.get("pyspark.sql")
    spark = mod.SparkSession.getActiveSession() if mod is not None else None
    if spark is None:
        raise RuntimeError(__NO_SESSION__)
    df = spark.sql(json.loads(payload))
    if not df.columns:
        display({"text/plain": "OK"}, raw=True)
    elif getattr(df, "isStreaming", False):
        display(df)
    else:
        # `_build`, not `render`: a runtime Spark error must surface as the
        # cell's error instead of being swallowed into the default repr.
        display(_build(df, MAX_ROWS), raw=True)
'''

_KERNEL_SOURCE = (
    _KERNEL_TEMPLATE.replace("__MAX_ROWS__", str(MAX_ROWS))
    .replace("__DISPLAY_ROWS__", str(DISPLAY_ROWS))
    .replace("__MAX_CELL_CHARS__", str(MAX_CELL_CHARS))
    .replace("__NO_SESSION__", repr(NO_SESSION_MESSAGE))
    .replace("__DUCKDB_MISSING__", repr(DUCKDB_MISSING_MESSAGE))
)
_VERSION = hashlib.sha1(_KERNEL_SOURCE.encode()).hexdigest()[:12]

# Runs via exec in a throwaway dict so the user's namespace gets no names. The
# module is reinstalled only when its version differs (its `STATE`, e.g. the DuckDB
# connection, is carried to the new module); `register` always runs
# (cheap, and recovers a reset formatter table) and is the only step whose
# failure is swallowed, so install errors surface to the caller.
_ENSURE_TEMPLATE = r'''
import sys, types
mod = sys.modules.get(__MODULE__)
if mod is None or getattr(mod, "VERSION", None) != __VERSION__:
    old_state = getattr(mod, "STATE", None)
    mod = types.ModuleType(__MODULE__)
    mod.VERSION = __VERSION__
    exec(__SOURCE__, mod.__dict__)
    if old_state:
        mod.STATE.update(old_state)
    sys.modules[__MODULE__] = mod
try:
    mod.register()
except Exception:
    pass
'''
_ENSURE_SOURCE = (
    _ENSURE_TEMPLATE.replace("__MODULE__", repr(MODULE_NAME))
    .replace("__VERSION__", repr(_VERSION))
    .replace("__SOURCE__", repr(_KERNEL_SOURCE))
)


def build_ensure_code() -> str:
    """Return the idempotent snippet that installs the renderer and its formatter."""
    return f"exec({_ENSURE_SOURCE!r}, {{}})"


def build_code(sql: str) -> str:
    """Return the Python source that runs `sql` and displays it as an HTML table."""
    guard = (
        "import sys\n"
        f"m = sys.modules.get({MODULE_NAME!r})\n"
        f"if m is None:\n    raise RuntimeError({RENDERER_MISSING_MESSAGE!r})\n"
        f"m.run({json.dumps(sql)!r})"
    )
    call = f"exec({guard!r}, {{}})"
    return f"{build_ensure_code()}\n{call}"


def build_duckdb_code(sql: str, ext_dir: str) -> str:
    """Return the Python source that runs one DuckDB statement and displays its result.

    `sql` and `ext_dir` (extension directory) travel as JSON string literals.
    """
    guard = (
        "import sys\n"
        f"m = sys.modules.get({MODULE_NAME!r})\n"
        f"if m is None:\n    raise RuntimeError({RENDERER_MISSING_MESSAGE!r})\n"
        f"m.run_duckdb({json.dumps(sql)!r}, {json.dumps(ext_dir)!r})"
    )
    call = f"exec({guard!r}, {{}})"
    return f"{build_ensure_code()}\n{call}"
