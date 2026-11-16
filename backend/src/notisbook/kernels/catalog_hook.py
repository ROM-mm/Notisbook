"""Hidden kernel module `_notisbook_catalog`: keeps the SparkSession in sync with `catalog.db`.

Installed by the same silent execute as the renderer. A `sys.meta_path` finder patches `getOrCreate`,
`stop`, `SparkSession.sql`, `DataFrameWriter(V2)` and `Catalog.createTable` (no pyspark import here). After a cell
(`post_run_cell`) it reconciles creations, changes, renames and drops with the `nb_*` registry; before one
(`pre_run_cell`) it picks up other kernels' writes. Only Delta/Parquet/Hudi tables of `spark_catalog` are
registered; Iceberg lives in its own catalog. Each session creates the four layers with `LOCATION s3a://notislake/<layer>`.
Before a write the destination rules run in Python and raise `Refused` (pt-BR text, nothing written): the
layer by schema, no overlap between tables, no repeated `<schema>.<t>`, no drop or move of a layer, path rules. Only a destination proven invalid is refused; a parser or registry failure lets the call go on, and the
post-write validation (`location_problem`, `apply_plan`) stays the second net. Writes outside Python are not covered.
s3a probes use the session's Hadoop FileSystem under a timeout and a 30 s breaker (`s3a_call`); the kernel deletes
only the `managed_table` folder the registry authorized. With `transport: "http"` (Docker) the registry goes through the backend API.
Config reaches the kernel as JSON literals; hook errors never reach the cell (kept in `STATE["errors"]`, warned once).
"""

import hashlib
import inspect
import json
from collections.abc import Mapping

from ..catalog.registry import apply_plan, read_snapshot
from ..notislake import locations as notislake_locations
from ..notislake.sparkconf import closed_options

MODULE_NAME = "_notisbook_catalog"

# Plain string (not an f-string); `build_ensure_code` substitutes __CONFIG__, __REGISTRY_HELPERS__ and __LOCATIONS_SOURCE__.
_KERNEL_TEMPLATE = r'''
import functools, importlib.abc, importlib.util, json, os, re, sqlite3, sys, threading, time, types
import urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

CONFIG = json.loads(__CONFIG__)
TRANSPORT = CONFIG.get("transport", "sqlite")
DB_PATH = CONFIG.get("db_path")
BASE_URL = CONFIG.get("base_url")
TOKEN = CONFIG.get("token")
# Folders shared with the runtime (http only): the backend rejects, item by item, a location outside them.
ROOTS = tuple(CONFIG.get("roots") or ())
WATCHED = ("pyspark.sql.session", "pyspark.sql.classic.session", "pyspark.sql.readwriter", "pyspark.sql.classic.readwriter",
           "pyspark.sql.catalog", "pyspark.sql.classic.catalog")
SUPPORTED = ("delta", "parquet") if TRANSPORT == "http" else ("delta", "parquet", "hudi")
# Tipo esperado do catálogo `iceberg`: o Docker fala REST com o backend; o local, JDBC direto no `catalog.db`.
ICEBERG_TYPE = "rest" if TRANSPORT == "http" else "jdbc"
S3A = CONFIG.get("s3a") or {}
S3A_PREFIX = "fs.s3a.bucket.notislake."
S3A_ROOT = "s3a://notislake/"
S3A_CLOSED = CONFIG["s3a_closed"]  # `sparkconf.closed_options()`, the single source of the closed bucket config
S3A_CLEARED = (S3A_PREFIX + "access.key", S3A_PREFIX + "secret.key")  # a failed setup may leave the real credential behind
S3A_SCHEME = "s3a://"
S3A_PROBE_TIMEOUT = 5.0  # one JVM call; with MinIO down only the first probe waits (the breaker then opens), so the hooks stay under 15 s
S3A_DELETE_BUDGET = 15.0  # ONE bound for every folder delete of a cell (not per table): N dropped tables never add N waits
S3A_PAUSE = 30.0  # circuit breaker: s3a probes stay suspended this long after a failure
HTTP_TIMEOUT = 8.0
HTTP_PAUSE = 30.0
HTTP_MAX_BYTES = 32 * 1024 * 1024
HTTP_DETAIL_BYTES = 4096
REJECTED = {
    "location_outside_mounts": "a location está fora das pastas compartilhadas com o runtime",
    "location_not_local": "a location não é uma pasta local",
    "managed_location_rejected": "a location gerenciada não tem a forma s3a://notislake/<camada>/<tabela>",
    "location_not_notislake": "a location s3a não é s3a://notislake/<camada>/<dataset>",
    "schema_not_layer": "o schema não é uma camada (landing, bronze, silver ou gold) e o notislake só recebe tabelas de camada",
    "not_notislake": "a location não é s3a://notislake/<camada>/<dataset> (s3:// e s3n:// não são aceitos)",
    "too_shallow": "a location precisa ter ao menos <camada>/<dataset>",
    "bad_segment": "a location ou o nome da tabela tem um segmento inválido ('.', '..', vazio ou com barra)",
    "outside_layer": "a location está fora da camada do schema da tabela",
    "overlaps_table": "a location sobrepõe a pasta de outra tabela",
    "name_in_other_catalog": "já existe uma tabela com o mesmo schema e nome no catálogo Iceberg",
    "item_limits": "o nome, o schema ou a descrição excedem os limites permitidos",
    "layer_protected": "as camadas landing, bronze, silver e gold não podem ser removidas nem mudar de location; "
                       "uma camada só é criada com a location dela (LOCATION 's3a://notislake/<camada>')",
    "name_in_spark_catalog": "já existe uma tabela com o mesmo schema e nome no catálogo do Spark (spark_catalog)",
}
# Escrita por path (sem tabela): o texto fala em caminho, não em schema da tabela.
REJECTED_PATH = {
    "outside_layer": "o caminho não está dentro de uma camada (landing, bronze, silver ou gold)",
    "too_shallow": "o caminho precisa ter ao menos <camada>/<dataset>; a raiz do bucket e a de uma camada não recebem gravação",
    "overlaps_table": "o caminho está dentro de, ou por cima de, outra tabela do catálogo",
}
ICEBERG_CATALOG = "iceberg"
FORMAT_NAMES = ("delta", "parquet", "orc", "json", "csv", "hudi", "text", "avro", "iceberg")  # `delta.`<path>`` addresses a folder
STATEMENT_RE = re.compile(r"\b(?:CREATE|REPLACE|INSERT|DROP|ALTER)\b", re.I)  # statements worth a parsePlan
TABLE_NODES = ("CreateTable", "CreateTableAsSelect", "ReplaceTable", "ReplaceTableAsSelect")
DEFAULT_DB = "default"
CATALOG = "spark_catalog"
# Cells that may change a table's schema/location without a new Delta commit (DDL words, never `.drop(`).
DEEP_RE = re.compile(
    r"\b(?:DROP\s+TABLE|ALTER\s+TABLE|REPLACE\s+TABLE|RENAME\s+TO|RECOVER\s+PARTITIONS|SET\s+LOCATION"
    r"|saveAsTable|insertInto)\b", re.I)
RENAME_RE = re.compile(r"\bRENAME\b", re.I)
LOG_RE = re.compile(r"^(\d{20})\.json$")
HUDI_INSTANT_RE = re.compile(r"^(\d+)_(\d+)\.(?:commit|deltacommit|replacecommit)$")
HUDI_V1_INSTANT_RE = re.compile(r"^(\d+)\.(?:commit|deltacommit|replacecommit)$")
OUTDATED = "This Spark environment predates the persistent catalog; reinstall Spark %s from the Spark versions panel."
MAX_ERRORS = 50
STATE = {}
BUSY = set()


def _load_locations():
    # Same source as `notislake/locations.py` (one rule set). `@dataclass` looks its module up in `sys.modules`, so it is there only while the source runs.
    module = types.ModuleType("_notisbook_locations")
    sys.modules[module.__name__] = module
    try:
        exec(__LOCATIONS_SOURCE__, module.__dict__)
    finally:
        sys.modules.pop(module.__name__, None)
    return module


LOCATIONS = _load_locations()


def warn(key, message):
    seen = STATE.setdefault("warned", set())
    if key in seen:
        return
    seen.add(key)
    try:
        print("Notisbook: " + message, file=sys.stderr)
    except Exception:
        pass


def short(exc):
    lines = str(exc).strip().splitlines()
    return (lines[0] if lines else type(exc).__name__)[:120]


def note_error(where, exc):
    errors = STATE.setdefault("errors", [])
    errors.append("%s: %s: %s" % (where, type(exc).__name__, exc))
    del errors[:-MAX_ERRORS]
    warn(("error", where), "catalog sync failed (%s): %s" % (where, short(exc)))


BYPASS = threading.local()
PENDING = threading.local()  # `stack`: one list of pending effects per active wrapped call of this thread


class Bypass:
    """While active, the hook's own Spark calls skip the pre-write checks (the hook never refuses itself)."""

    def __enter__(self):
        BYPASS.depth = getattr(BYPASS, "depth", 0) + 1

    def __exit__(self, *exc):
        BYPASS.depth -= 1


def guarded(where, fn, *args):
    # A hook failure must never surface in the user's cell.
    try:
        with Bypass():
            return fn(*args)
    except S3AUnavailable:
        return None  # already warned once by the breaker; the next cell retries
    except Exception as exc:
        note_error(where, exc)
        return None


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_path(location):
    if not location:
        return None
    if location.startswith("file:"):
        return unquote(urlparse(location).path)
    if "://" in location:
        return None
    return location if os.path.isabs(location) else None


def is_s3a(location):
    return isinstance(location, str) and location.startswith(S3A_SCHEME)


def notislake_uri(location):
    """Canonical `s3a://notislake/<a>/<b>[/...]` of a valid location, else None."""
    try:
        return LOCATIONS.parse_notislake(location).uri
    except LOCATIONS.InvalidLocation:
        return None


def norm_loc(location):
    # Same form the backend's Iceberg reader returns (`Path.as_uri()`): one location format in the API.
    if is_s3a(location):
        return notislake_uri(location) or location
    path = local_path(location)
    return Path(path).as_uri() if path else location


def location_problem(key, location):
    """Code of `REJECTED` when the table `key` cannot live at `location`, else None.

    Only what is decidable here: layer by schema, shape and (http) shared folders. Overlap with other tables
    and the name repeated in Iceberg are decided by the registry (`apply_plan`, which sees both catalogs).
    """
    if is_s3a(location):
        if not LOCATIONS.targets_notislake(location):
            return "location_not_notislake"
        try:
            LOCATIONS.table_destination(key[0], key[1], location, ())
        except LOCATIONS.InvalidLocation as exc:
            return exc.code
        return None
    if LOCATIONS.targets_notislake(location):
        return "not_notislake"
    if not ROOTS:
        return None
    path = local_path(location)
    inside = bool(path) and any(is_under(path, r) and path.rstrip("/") != r.rstrip("/") for r in ROOTS)
    return None if inside else "location_outside_mounts"


def reject_text(key, code):
    return "a tabela %s.%s não foi salva no catálogo persistente: %s." % (*key, REJECTED.get(code, code))


def is_under(location, root, fold=False):
    """True when `location` is `root` or inside it (compared with a trailing separator: `a/iceberg` is not `a/iceberg_raw`).

    `fold` ignores case (APFS); use it only to refuse more, never to allow.
    """
    loc, base = location.rstrip("/") + "/", root.rstrip("/") + "/"
    if fold:
        loc, base = loc.casefold(), base.casefold()
    return loc.startswith(base)


class S3AUnavailable(Exception):
    """s3a probes are suspended (circuit breaker open) or the call failed/timed out; callers keep the last known state."""


def s3a_trip(session):
    STATE["s3a_open_until"] = time.monotonic() + S3A_PAUSE
    # Fixed text: Hadoop messages may echo the endpoint or the key.
    warn(("s3a-down", session_key(session)), "s3a://notislake/ did not answer; its tables are not checked for %d s." % S3A_PAUSE)


def s3a_call(session, fn, timeout=S3A_PROBE_TIMEOUT, bulk=False):
    """Run `fn(fs_for)` (JVM calls on the session's Hadoop FileSystem) bounded by `timeout`; raises S3AUnavailable.

    A Hadoop call to a dead endpoint retries for minutes and py4j cannot interrupt it, so it runs in a daemon
    thread that is abandoned on timeout; while that thread lives no other call of its kind starts (they would pile up).
    A probe failure opens the breaker (no probe for `S3A_PAUSE`, one warning). A `bulk` call (deleting folders) has
    its own thread slot and never opens it: a slow delete says nothing about the endpoint, and its still-running
    thread must not make the next probe look like a pile-up.
    A missing path is not a failure: `fn` reports it by its return value (`exists` is False, not an exception).
    Without a working S3A setup in the session nothing is probed: the bucket would resolve to the public AWS endpoint.
    """
    status = s3a_status(session)
    if status != "ok":
        if status != "failed":  # a failed setup already warned
            warn(("s3a-unset", session_key(session)), "S3A is not configured in this session; s3a://notislake/ tables are not checked.")
        raise S3AUnavailable()
    if time.monotonic() < STATE.get("s3a_open_until", 0.0):
        raise S3AUnavailable()
    slot = "s3a_bulk" if bulk else "s3a_probe"

    def fail():
        if not bulk:
            s3a_trip(session)
        raise S3AUnavailable()

    previous = STATE.get(slot)
    if previous is not None and previous.is_alive():
        fail()
    sc = session.sparkContext
    box = {}

    def run():
        try:
            jvm, conf = sc._jvm, sc._jsc.hadoopConfiguration()

            def open_path(uri):
                path = jvm.org.apache.hadoop.fs.Path(uri)
                return path, path.getFileSystem(conf)
            box["value"] = fn(open_path)
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=run, name="notisbook-s3a-bulk" if bulk else "notisbook-s3a-probe", daemon=True)
    STATE[slot] = thread
    thread.start()
    thread.join(timeout)
    if thread.is_alive() or "error" in box:
        fail()
    STATE["s3a_open_until"] = 0.0
    return box["value"]


def retry_when_reachable(session):
    """Ask for another registry pass once the breaker reopens; pointless without a working S3A setup."""
    if s3a_status(session) == "ok":
        STATE["resync"] = True


def s3a_names(session, location, sub=""):
    """Entry names of `<location>/<sub>` in the bucket; None when the folder does not exist."""
    base = notislake_uri(location) if session is not None else None
    if base is None:
        raise S3AUnavailable()
    target = base + "/" + sub if sub else base

    def listing(open_path):
        path, fs = open_path(target)
        if not fs.exists(path):
            return None
        return [status.getPath().getName() for status in fs.listStatus(path)]
    return s3a_call(session, listing)


def s3a_exists(session, location, sub=""):
    base = notislake_uri(location) if session is not None else None
    if base is None:
        raise S3AUnavailable()
    target = base + "/" + sub if sub else base

    def check(open_path):
        path, fs = open_path(target)
        return bool(fs.exists(path))
    return s3a_call(session, check)


def delta_versions(location, session=None):
    if is_s3a(location):
        return [int(m.group(1)) for m in map(LOG_RE.match, s3a_names(session, location, "_delta_log") or []) if m]
    base = local_path(location)
    if not base:
        return []
    try:
        names = os.listdir(os.path.join(base, "_delta_log"))
    except OSError:
        return []
    return [int(m.group(1)) for m in map(LOG_RE.match, names) if m]


def delta_version(location, session=None):
    versions = delta_versions(location, session)
    return max(versions) if versions else None


def delta_advanced(location, version, session=None):
    if is_s3a(location):
        if version is None:
            return delta_version(location, session) is not None
        return s3a_exists(session, location, "_delta_log/%020d.json" % (version + 1))
    base = local_path(location)
    if not base:
        return False
    if version is None:
        return delta_version(location) is not None
    return os.path.exists(os.path.join(base, "_delta_log", "%020d.json" % (version + 1)))


def latest_hudi_instant(timeline, hoodie):
    """Latest completed instant from the names of `.hoodie/timeline` (None when the folder is missing) and `.hoodie`."""
    if timeline is None:
        legacy = [m.group(1) for m in map(HUDI_V1_INSTANT_RE.match, hoodie() or []) if m]
        return max(legacy, key=int) if legacy else None
    done = [m.groups() for m in map(HUDI_INSTANT_RE.match, timeline) if m]
    if not done:
        return None
    req, comp = max(done, key=lambda g: (int(g[1]), int(g[0])))
    return "%s_%s" % (req, comp)


def hudi_instant(location, session=None):
    """Marker of the latest completed Hudi instant, or None (`.requested`/`.inflight` and dotfiles never match).

    Layout v2 (`.hoodie/timeline/<req>_<comp>.<action>`): ordered by completion time, so a commit that finishes
    out of order still moves the marker; returns `<req>_<comp>`. Layout v1 (no `timeline/` folder, Hudi 0.x):
    `.hoodie/<ts>.<action>`, returns `<ts>`.
    """
    if is_s3a(location):
        return latest_hudi_instant(s3a_names(session, location, ".hoodie/timeline"),
                                   lambda: s3a_names(session, location, ".hoodie"))
    base = local_path(location)
    if not base:
        return None
    hoodie = os.path.join(base, ".hoodie")
    try:
        timeline = os.listdir(os.path.join(hoodie, "timeline"))
    except FileNotFoundError:
        timeline = None
    except OSError:
        return None

    def legacy_names():
        try:
            return os.listdir(hoodie)
        except OSError:
            return None
    return latest_hudi_instant(timeline, legacy_names)


__REGISTRY_HELPERS__


def delete_managed_s3a(session, items):
    """Delete the bucket folders of dropped MANAGED tables under ONE time budget; returns `{key: error text or None}`.

    `items` is `[(key, location)]`, each the folder the registry row authorized (`apply_plan` already checked there
    is no other use); here it must also have the `managed_table` shape, so never the warehouse, a `*.db` folder or a
    prefix of it. One thread deletes them in order within `S3A_DELETE_BUDGET`. When the budget runs out the thread is
    cancelled before its next folder (a table recreated with the same name must not lose its new files); only the
    delete already running can still land. Folders without a result are reported as kept. Texts are fixed: Hadoop
    messages may echo the endpoint.
    """
    outcome, todo, done = {}, [], {}
    for key, location in items:
        uri = notislake_uri(location)
        if session is None or uri is None or not LOCATIONS.managed_table(uri):
            outcome[key] = "location is not a managed table folder"
        else:
            todo.append((key, uri))
    if not todo:
        return outcome

    cancelled = threading.Event()

    def remove_all(open_path):
        deadline = time.monotonic() + S3A_DELETE_BUDGET
        for key, uri in todo:
            if cancelled.is_set() or time.monotonic() >= deadline:
                return
            try:
                path, fs = open_path(uri)
                if fs.exists(path):
                    fs.delete(path, True)
                done[key] = None if not fs.exists(path) else "the bucket still lists the folder"
            except Exception:
                done[key] = "the delete failed; the files may remain"
    try:
        s3a_call(session, remove_all, S3A_DELETE_BUDGET, bulk=True)
    except S3AUnavailable:
        cancelled.set()
    finished = dict(done)
    for key, _uri in todo:
        outcome[key] = finished[key] if key in finished else "s3a://notislake/ did not finish in time or is not configured; the files may remain"
    return outcome


def connect():
    # mode=rw: the backend creates catalog.db; a missing file must not become an empty database.
    conn = sqlite3.connect("file:%s?mode=rw" % quote(DB_PATH), uri=True, isolation_level=None, timeout=10.0)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def read_generation(conn):
    row = conn.execute("SELECT value FROM nb_meta WHERE key = 'generation'").fetchone()
    return int(row[0]) if row else 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # the Authorization header must never follow a redirect


# No proxy from the environment either: the token goes only to the backend.
HTTP_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def http_pause(seconds):
    STATE["http_pause"] = time.monotonic() + seconds


def http_detail(exc):
    """Short `detail` of a 4xx answer (text of the first validation error), cut and without the token; '' if unreadable."""
    try:
        detail = json.loads(exc.read(HTTP_DETAIL_BYTES))["detail"]
        if isinstance(detail, list):
            detail = "%s: %s" % (".".join(map(str, detail[0]["loc"])), detail[0]["msg"])
        return str(detail).replace(TOKEN, "")[:120]
    except Exception:
        return ""


def http_call(method, path, payload=None):
    """JSON call to the backend catalog API; errors carry a short generic text (never the URL or the token)."""
    if time.monotonic() < STATE.get("http_pause", 0.0):
        raise RuntimeError("catalog API unreachable (retrying shortly)")
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    try:
        with HTTP_OPENER.open(request, timeout=HTTP_TIMEOUT) as response:
            body = response.read(HTTP_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        code = exc.code
        detail = http_detail(exc) if code == 422 else ""
        exc.close()
        if code in (401, 403) or code >= 500:
            http_pause(HTTP_PAUSE if code < 500 else 5.0)
        raise RuntimeError("catalog API answered HTTP %d%s" % (code, " (%s)" % detail if detail else "")) from None
    except (urllib.error.URLError, OSError):
        http_pause(HTTP_PAUSE)
        raise RuntimeError("catalog API unreachable") from None
    if len(body) > HTTP_MAX_BYTES:
        raise RuntimeError("catalog API answer too large")
    return json.loads(body)


def current_generation():
    if TRANSPORT == "http":
        return int(http_call("GET", "/generation")["generation"])
    conn = connect()
    try:
        return read_generation(conn)
    finally:
        conn.close()


def read_registry():
    if TRANSPORT == "http":
        data = http_call("GET", "/registry")
        rows = {(t["db"], t["name"]): {k: t[k] for k in ("fmt", "loc", "type", "cols", "parts", "dv", "hi")}
                for t in data["tables"] if t["fmt"] in SUPPORTED}
        return int(data["generation"]), rows, set(data["namespaces"])
    conn = connect()
    try:
        return read_snapshot(conn)
    finally:
        conn.close()


def write_txn(fn):
    """Run `fn(conn)` in one short BEGIN IMMEDIATE; a truthy result bumps `generation`.

    No JVM call may happen inside `fn`: the writer lock is held for the transaction only.
    """
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            before = read_generation(conn)
            changed = fn(conn)
            after = before + 1 if changed else before
            if changed:
                conn.execute("UPDATE nb_meta SET value = ? WHERE key = 'generation'", (str(after),))
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    finally:
        conn.close()
    if changed and before == STATE.get("gen"):
        STATE["gen"] = after  # our own write, nothing of others' unseen
    return changed


def quote_ident(part):
    return "`" + part.replace("`", "``") + "`"


def ns_ident(db):
    # Always qualified: the session's current catalog may not be `spark_catalog` (`USE iceberg`).
    return CATALOG + "." + quote_ident(db)


def ident(db, name):
    return ns_ident(db) + "." + quote_ident(name)


def conf_get(session, key):
    try:
        return session.conf.get(key, None)
    except Exception:
        return None


def session_key(session):
    sc = session.sparkContext
    return "%s:%s" % (sc.applicationId, sc.startTime)


def session_alive(session):
    try:
        return session.sparkContext._jsc is not None
    except Exception:
        return False


def current_session():
    module = sys.modules.get("pyspark.sql.session")
    cls = getattr(module, "SparkSession", None)
    if cls is None:
        return None
    session = None
    try:
        session = cls.getActiveSession()
    except Exception:
        pass
    if session is None:
        session = getattr(cls, "_instantiatedSession", None)
    # Spark Connect sessions have no JVM handle and are out of scope.
    if session is None or getattr(session, "_jsparkSession", None) is None or not session_alive(session):
        return None
    return session


def list_catalog(session):
    """(databases, {(db, table): Table}, databases whose listing failed) of `spark_catalog`; temp views are skipped.

    Raises when the listing cannot be vouched for as coming from `spark_catalog`, so that no caller
    reads a missing table as a dropped one.
    """
    dbs = [row[0] for row in session.sql("SHOW NAMESPACES IN " + CATALOG).collect()]
    if DEFAULT_DB not in dbs:
        raise RuntimeError("the namespace listing does not look like the one of " + CATALOG)
    tables, failed = {}, set()
    for db in dbs:
        try:
            listed = session.catalog.listTables(ns_ident(db))
        except Exception:
            failed.add(db)
            continue
        for t in listed:
            if t.isTemporary:
                continue
            if getattr(t, "catalog", None) not in (None, CATALOG):
                raise RuntimeError("table %s.%s was listed from catalog %s" % (db, t.name, t.catalog))
            tables[(db, t.name)] = t
    return dbs, tables, failed


def read_columns(session, db, name):
    return [
        {"name": c.name, "data_type": c.dataType, "nullable": bool(c.nullable),
         "is_partition": bool(c.isPartition), "description": c.description}
        for c in session.catalog.listColumns(ident(db, name))
    ]


def table_columns(session, key, parts):
    # The table schema (latest snapshot/commit), not the catalog copy, which can lag behind other kernels' commits.
    fields = session.table(ident(*key)).schema.fields
    return [
        {"name": f.name, "data_type": f.dataType.simpleString(), "nullable": bool(f.nullable),
         "is_partition": f.name in parts, "description": (f.metadata or {}).get("comment")}
        for f in fields
    ]


def read_info(session, db, name):
    detail, seen = {}, False
    for row in session.sql("DESCRIBE TABLE EXTENDED " + ident(db, name)).collect():
        label = row[0] or ""
        if label.startswith("# Detailed Table Information"):
            seen = True
        elif seen and label:
            detail[label] = row[1]
    return {"provider": (detail.get("Provider") or "").lower(), "location": detail.get("Location"),
            "columns": read_columns(session, db, name)}


def describe_new(session, key, table):
    """Registry record for a table that appeared in the session; None (with a warning) when unsupported."""
    skey = session_key(session)
    label = "%s.%s" % key
    if table.tableType == "VIEW":
        warn(("view", skey, key), "persistent view %s is not saved in the persistent catalog." % label)
        return None
    info = read_info(session, *key)
    if info["provider"] not in SUPPORTED:
        warn(("format", skey, key), "table %s uses format '%s'; it is not saved in the persistent catalog." % (label, info["provider"]))
        return None
    loc = norm_loc(info["location"])
    problem = location_problem(key, loc)
    if problem:
        warn(("rejected", skey, key), reject_text(key, problem))
        return None
    fmt = info["provider"]
    parts = [c["name"] for c in info["columns"] if c["is_partition"]]
    typ = "EXTERNAL" if table.tableType == "MANAGED" and not managed_shape(loc) else table.tableType
    return {"fmt": fmt, "loc": loc, "type": typ, "cols": info["columns"], "parts": parts,
            "dv": delta_version(loc, session) if fmt == "delta" else None,
            "hi": hudi_instant(loc, session) if fmt == "hudi" else None, "description": table.description}


def s3a_reachable(session, location):
    """True when the bucket answers; the Spark reads that follow (schema, `DESCRIBE`) have no timeout of their own."""
    try:
        s3a_exists(session, location)
    except S3AUnavailable:
        return False
    return True


def hydrate(session, skey, rows, namespaces, listing=None):
    """Create in the session the registry tables it lacks; returns the registry keys it skipped."""
    known = STATE.setdefault("known", {}).setdefault(skey, {})
    known_dbs = STATE.setdefault("known_dbs", {}).setdefault(skey, set())
    dbs, current, _ = listing or list_catalog(session)
    for ns in sorted(namespaces - {DEFAULT_DB} - set(LOCATIONS.LAYERS)):  # layers: only `ensure_layers`, which sets their LOCATION
        if ns not in dbs:
            try:
                session.sql("CREATE DATABASE IF NOT EXISTS " + ns_ident(ns))
            except Exception:
                continue
        known_dbs.add(ns)
    skipped, refresh = [], []
    for key, row in sorted(rows.items()):
        if key in known or key in current:
            continue
        path = local_path(row["loc"])
        if path is not None and not os.path.exists(path):
            skipped.append(key)
            continue
        if is_s3a(row["loc"]):
            try:
                present = s3a_exists(session, row["loc"])
            except S3AUnavailable:
                retry_when_reachable(session)  # not a final verdict (and no second warning)
                continue
            if not present:
                skipped.append(key)
                continue
        try:
            session.catalog.createTable(ident(*key), path=path or row["loc"], source=row["fmt"])
            if row["parts"] and row["fmt"] == "parquet":
                session.sql("ALTER TABLE %s RECOVER PARTITIONS" % ident(*key))
        except Exception:
            skipped.append(key)
            continue
        known[key] = {**row, "sess_managed": False}
        refresh.append(key)
    if skipped:
        names = ", ".join("%s.%s" % k for k in skipped[:3]) + (", ..." if len(skipped) > 3 else "")
        warn(("skipped", skey, tuple(skipped)), "could not load %d catalog table(s) (missing path or unavailable format): %s" % (len(skipped), names))
    return refresh


def refresh_hydrated(session, skey, keys):
    """Update registry schemas that drifted from the real table (Delta by log version, Hudi by instant, Parquet by schema)."""
    known = STATE["known"][skey]
    changes, leaving = [], []
    for key in keys:
        change = refresh_table(session, key, known[key], deep=known[key]["fmt"] == "parquet")
        if change == LEAVE:
            leaving.append(key)
        elif change:
            changes.append((key, change))
    if changes or leaving:
        STATE.setdefault("ignored", {}).setdefault(skey, set()).update(leaving)
        apply_changes(skey, [], changes, [], leaving, set(), set(), keep_files=set(leaving), session=session)


def set_iceberg_token(session):
    """Put the runtime token of the `iceberg` (REST) catalog in the session conf, not in the spark-submit argv (visible in `ps`).

    Spark only reads `spark.sql.catalog.iceberg.*` when it loads the catalog, on first use.
    """
    if TRANSPORT == "http" and TOKEN:
        guarded("iceberg-token", session.conf.set, "spark.sql.catalog.iceberg.token", TOKEN)


def s3a_status(session=None):
    """`off` without `s3a` in the config, else `pending`, `ok` or `failed` for the session's SparkContext."""
    if not S3A:
        return "off"
    session = session or current_session()
    if session is None:
        return "pending"
    return STATE.get("s3a_status", {}).get(session_key(session), "pending")


def close_s3a_bucket(session):
    """Point the `notislake` bucket at a dead loopback endpoint without credentials.

    A session without a working S3A setup would otherwise resolve the bucket to the public AWS endpoint
    with the default credential chain; here it fails closed (connection refused).
    """
    hadoop_conf = session.sparkContext._jsc.hadoopConfiguration()
    for key, value in S3A_CLOSED.items():
        hadoop_conf.set(key, value)
    for key in S3A_CLEARED:
        hadoop_conf.set(key, "")
    renew_s3a_fs(session, hadoop_conf)


def renew_s3a_fs(session, hadoop_conf):
    """Replace the cached FileSystem of the bucket by one built from `hadoop_conf` and keep a reference to it.

    `FileSystem.get` returns one cached instance per scheme+authority+user whatever the conf of the caller, so the
    first one created wins: the old one (made before the credential) is closed, the new one is created now and held
    in STATE, and a later clone of the SparkSession without the credential finds it in the cache instead of filling it.
    """
    jvm = session.sparkContext._jvm
    uri = jvm.java.net.URI.create(S3A_ROOT)
    jvm.org.apache.hadoop.fs.FileSystem.get(uri, hadoop_conf).close()
    STATE.setdefault("s3a_fs", {})[session_key(session)] = jvm.org.apache.hadoop.fs.FileSystem.get(uri, hadoop_conf)


def set_s3a(session):
    """Write the S3A options of the `notislake` bucket in the Hadoop conf, once per SparkContext.

    Runs after the original `getOrCreate`: through the builder `.config()` the secret would become a
    `--conf` of the spark-submit argv (visible in `ps`). The cached FileSystem of the bucket is renewed
    and kept (`renew_s3a_fs`) so the new credentials apply. The warning is fixed text: Hadoop messages may echo the key.
    Without `s3a` in the config, or when the setup fails, the bucket is closed (`close_s3a_bucket`).
    """
    skey = session_key(session)
    done = STATE.setdefault("s3a_done", set())
    if skey in done:
        return
    done.add(skey)
    if not S3A:
        close_s3a_bucket(session)
        return
    status = "ok"
    try:
        if not all(key.startswith(S3A_PREFIX) for key in S3A):
            raise ValueError("unexpected S3A key")
        sc = session.sparkContext
        hadoop_conf = sc._jsc.hadoopConfiguration()
        for key, value in S3A.items():
            hadoop_conf.set(key, str(value))
        renew_s3a_fs(session, hadoop_conf)
    except Exception as exc:
        status = "failed"
        STATE.setdefault("errors", []).append("s3a: %s" % type(exc).__name__)
        del STATE["errors"][:-MAX_ERRORS]
        warn(("s3a", skey), "S3A setup failed; s3a://notislake/ may be unavailable in this session.")
        try:
            close_s3a_bucket(session)
        except Exception:  # the status already blocks every probe of the hook
            pass
    STATE.setdefault("s3a_status", {})[skey] = status


def layer_location(session, layer):
    rows = session.sql("DESCRIBE NAMESPACE EXTENDED " + ns_ident(layer)).collect()
    return next((r[1] for r in rows if str(r[0]).lower() == "location"), None)


def ensure_layers(session, skey, dbs=None):
    """Make `spark_catalog` hold the four layers with `LOCATION s3a://notislake/<layer>`; `dbs` is a listing already at hand.

    A missing layer gets its bucket folder first (one bounded s3a call: `CREATE DATABASE` makes it unbounded),
    then `CREATE DATABASE IF NOT EXISTS`. A layer that already exists keeps its location and is never dropped
    or altered (a drop would delete files, and v1 `SET LOCATION` is unsupported): it is warned once, since
    its MANAGED tables would then miss the notislake. Raises S3AUnavailable (a later pass retries) when the bucket is unreachable.
    """
    if dbs is None:
        dbs = [row[0] for row in session.sql("SHOW NAMESPACES IN " + CATALOG).collect()]
    missing = [layer for layer in LOCATIONS.LAYERS if layer not in dbs]
    if missing:
        def make_folders(open_path):
            for layer in missing:
                path, fs = open_path(LOCATIONS.layer_uri(layer))
                fs.mkdirs(path)
        try:
            s3a_call(session, make_folders)
        except S3AUnavailable:
            retry_when_reachable(session)
            raise
        for layer in missing:
            session.sql("CREATE DATABASE IF NOT EXISTS %s LOCATION '%s'" % (ns_ident(layer), LOCATIONS.layer_uri(layer)))
    checked = STATE.setdefault("layers_checked", {}).setdefault(skey, set())
    for layer in LOCATIONS.LAYERS:
        if layer in checked:
            continue
        location = layer_location(session, layer)
        checked.add(layer)  # only after the DESCRIBE answered: a failure leaves the layer to be checked again
        if (location or "").rstrip("/") != LOCATIONS.layer_uri(layer):
            warn(("layer", skey, layer), "a camada %s já existia nesta sessão com outra location; as tabelas gerenciadas dela não vão para s3a://notislake/%s." % (layer, layer))


def attach(session):
    if getattr(session, "_jsparkSession", None) is None:
        return
    # Sessions made by `SparkSession(sc)` or `newSession()` never pass through getOrCreate.
    # Credential first: the FileSystem that Spark builds later must already find the bucket configured.
    guarded("s3a", set_s3a, session)
    set_iceberg_token(session)
    skey = session_key(session)
    if skey in STATE.setdefault("attached", set()) or skey in STATE.setdefault("off", set()):
        return
    if conf_get(session, "spark.sql.catalogImplementation") == "hive":
        STATE["off"].add(skey)
        warn(("hive", skey), "Hive support is active; the persistent catalog is off for this session.")
        return
    if conf_get(session, "spark.sql.catalog.iceberg") and conf_get(session, "spark.sql.catalog.iceberg.type") != ICEBERG_TYPE:
        warn(("outdated", skey), OUTDATED % session.version)
    guarded("layers", ensure_layers, session, skey)
    gen, rows, namespaces = read_registry()
    refresh = hydrate(session, skey, rows, namespaces | {k[0] for k in rows})
    STATE["gen"] = None if STATE.pop("resync", False) else gen
    STATE["attached"].add(skey)
    guarded("refresh", refresh_hydrated, session, skey, refresh)


def db_folder_is_empty(session, ns):
    """True when the session's folder for the database is missing or empty; any doubt (non-local, error) is False."""
    try:
        rows = session.sql("DESCRIBE NAMESPACE EXTENDED " + ns_ident(ns)).collect()
    except Exception:
        return False
    loc = next((r[1] for r in rows if str(r[0]).lower() == "location"), None)
    path = local_path(loc)
    if not path:
        return False
    if not os.path.isdir(path):
        return not os.path.lexists(path)
    try:
        return not os.listdir(path)
    except OSError:
        return False


def drop_removed_db(session, ns, session_dbs, known_dbs, tombstones):
    """Apply, in the session, a namespace removed from the registry without ever deleting files.

    The Spark DROP DATABASE removes the folder recursively (EXTERNAL data included), so it only runs on an
    empty folder; otherwise the namespace is tombstoned: the session keeps it and the sync stops reconsidering it.
    """
    if ns not in session_dbs:
        known_dbs.discard(ns)
        return
    if not db_folder_is_empty(session, ns):
        tombstones.add(ns)
        return
    try:
        session.sql("DROP DATABASE IF EXISTS " + ns_ident(ns))
    except Exception:
        # Without a tombstone the sync would repeat the DROP (and its failure) on every cell.
        tombstones.add(ns)
        return
    known_dbs.discard(ns)


def files_exist(session, location):
    """True when the table's files exist (local folder, or s3a objects); an unreachable bucket counts as existing, so nothing is dropped blindly."""
    if is_s3a(location):
        try:
            return s3a_exists(session, location)
        except S3AUnavailable:
            retry_when_reachable(session)
            return True
    path = local_path(location)
    return bool(path and os.path.exists(path))


def sync_registry(session, skey):
    """Before a cell: bring in what other kernels registered or dropped since the last look."""
    if current_generation() == STATE.get("gen"):
        return
    gen, rows, namespaces = read_registry()
    # Without a reliable spark_catalog listing nothing is dropped or hydrated in this cell.
    listing = list_catalog(session)
    if any(layer not in listing[0] for layer in LOCATIONS.LAYERS):
        guarded("layers", ensure_layers, session, skey, listing[0])
        listing = list_catalog(session)
    known = STATE["known"].setdefault(skey, {})
    for key, rec in list(known.items()):
        if key in rows:
            continue
        # A table this session created as MANAGED would take its files with it on DROP: keep it while they exist.
        if not (rec.get("sess_managed") and files_exist(session, rec["loc"])):
            try:
                session.sql("DROP TABLE IF EXISTS " + ident(*key))
            except Exception:
                pass
            known.pop(key)
    all_ns = namespaces | {k[0] for k in rows}
    known_dbs = STATE.setdefault("known_dbs", {}).setdefault(skey, set())
    tombstones = STATE.setdefault("tombstones", {}).setdefault(skey, set())
    tombstones &= known_dbs - all_ns
    for ns in sorted(known_dbs - all_ns - tombstones):
        drop_removed_db(session, ns, listing[0], known_dbs, tombstones)
    refresh = hydrate(session, skey, rows, all_ns, listing)
    STATE["gen"] = None if STATE.pop("resync", False) else gen
    guarded("refresh", refresh_hydrated, session, skey, refresh)


LEAVE = "leave"


def refresh_table(session, key, rec, deep):
    """Changed fields of a known table, None, or LEAVE. `deep` rereads location/format/schema from Spark.

    LEAVE: the location moved to a place `location_problem` refuses; the caller
    unregisters the table (warned once) so no session rehydrates the old path. While s3a probes are
    suspended the table keeps its last known state (None).
    """
    try:
        if deep and is_s3a(rec["loc"]) and not s3a_reachable(session, rec["loc"]):
            return None
        return probe_table(session, key, rec, deep)
    except S3AUnavailable:
        return None


def probe_table(session, key, rec, deep):
    fmt, loc, cols, parts, dv = rec["fmt"], rec["loc"], rec["cols"], rec["parts"], rec["dv"]
    hi = rec.get("hi")  # absent in records carried over from a hook version that predates Hudi
    if deep:
        info = read_info(session, *key)
        if info["provider"] in SUPPORTED:
            fmt, loc, cols = info["provider"], norm_loc(info["location"]), info["columns"]
            parts = [c["name"] for c in cols if c["is_partition"]]
    if fmt == "delta" and (deep or delta_advanced(loc, dv, session)):
        cols = table_columns(session, key, parts)
        dv = delta_version(loc, session)
    cur = hudi_instant(loc, session) if fmt == "hudi" else None  # read before the schema: a commit in between is seen next time
    if fmt == "hudi" and (deep or cur != hi):
        cols = table_columns(session, key, parts)
        hi = cur
    new = {"fmt": fmt, "loc": loc, "cols": cols, "parts": parts, "dv": dv, "hi": hi}
    if loc != rec["loc"]:
        problem = location_problem(key, loc)
        if problem:
            warn(("rejected", session_key(session), key), reject_text(key, problem))
            return LEAVE
    return None if all(new[f] == rec.get(f) for f in new) else new


def match_renames(vanished, appeared, known, raw_cell):
    """Triples (old, new, info): same location, or a unique same-format/schema pair (managed folder moved by RENAME).

    The format/schema fallback applies only when the cell has a `RENAME`: `DROP a` + `CREATE b` is not a rename.
    """
    pairs = []
    renamed_cell = bool(raw_cell and RENAME_RE.search(raw_cell))
    for old in list(vanished):
        rec = known[old]
        cands = [n for n, info in appeared.items() if info["loc"] == rec["loc"]]
        if not cands and renamed_cell:
            same = [n for n, info in appeared.items() if (info["fmt"], info["cols"]) == (rec["fmt"], rec["cols"])]
            peers = [o for o in vanished if (known[o]["fmt"], known[o]["cols"]) == (rec["fmt"], rec["cols"])]
            cands = same if len(same) == 1 and len(peers) == 1 else []
        if len(cands) == 1:
            pairs.append((old, cands[0], appeared.pop(cands[0])))
            vanished.remove(old)
    return pairs


def wire_info(info):
    return {k: info[k] for k in ("fmt", "loc", "cols", "parts", "dv", "hi")}


def wire_deletions(raw):
    """Keep only the `(key, loc)` removals the backend authorized with a well-formed key and a MANAGED-shaped s3a `loc`."""
    out = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict):
            continue
        key, loc = item.get("key"), item.get("loc")
        if (isinstance(key, (list, tuple)) and len(key) == 2 and all(isinstance(p, str) for p in key)
                and isinstance(loc, str) and LOCATIONS.managed_table(loc)):
            out.append((tuple(key), loc))
    return out


def commit_http(plan):
    """POST the plan; the backend decides types and deletes MANAGED files, and answers in the shape `apply_plan` returns."""
    body = {
        "created": [{"db": k[0], "name": k[1], "type": i["type"], "description": i.get("description"), **wire_info(i)}
                    for k, i in plan["created"]],
        "updated": [{"db": k[0], "name": k[1], "expected_loc": loc, **wire_info(c)} for k, loc, _t, c in plan["updated"]],
        "renamed": [{"old_db": o[0], "old_name": o[1], "new_db": n[0], "new_name": n[1], "expected_loc": loc,
                     **wire_info(i)} for o, n, loc, i in plan["renamed"]],
        "dropped": [{"db": k[0], "name": k[1], "expected_loc": loc} for k, loc in plan["dropped"]],
        "unregistered": [{"db": k[0], "name": k[1], "expected_loc": loc} for k, loc in plan.get("unregistered", ())],
        "new_dbs": sorted(plan["new_dbs"]),
        "gone_dbs": sorted(plan["gone_dbs"]),
    }
    reply = http_call("POST", "/plan", body)
    changes = {k: c for k, _l, _t, c in plan["updated"]}
    infos = {(o, n): i for o, n, _l, i in plan["renamed"]}
    out = {"changed": bool(reply["changed"]), "deletions": wire_deletions(reply.get("deletions", [])),
           "adopted": [tuple(k) for k in reply["adopted"]],
           "conflicts": [tuple(k) for k in reply["conflicts"]],
           "dropped_ok": [tuple(k) for k in reply["dropped_ok"]],
           "files_kept": [tuple(k) for k in reply.get("files_kept", [])],
           "rejected": [(tuple(r["key"]), str(r["reason"])) for r in reply.get("rejected", [])],
           "updated_ok": [(tuple(u["key"]), {**changes[tuple(u["key"])], "type": u["type"]})
                          for u in reply["updated_ok"] if tuple(u["key"]) in changes],
           "renamed_ok": [(tuple(r["old"]), tuple(r["new"]), infos[(tuple(r["old"]), tuple(r["new"]))])
                          for r in reply["renamed_ok"] if (tuple(r["old"]), tuple(r["new"])) in infos]}
    if out["changed"] and reply["generation_before"] == STATE.get("gen"):
        STATE["gen"] = reply["generation"]  # our own write, nothing of others' unseen
    return out


def commit_plan(plan, stamp):
    if TRANSPORT == "http":
        return commit_http(plan)
    result = {}

    def fn(conn):
        result.update(apply_plan(conn, plan, stamp, managed_shape,
                                 destination=LOCATIONS.table_destination, protected_dbs=LOCATIONS.LAYERS))
        return result["changed"]

    write_txn(fn)
    return result


def apply_changes(skey, created, updated, renamed, dropped, new_dbs, gone_dbs, keep_files=frozenset(), session=None):
    """Write the plan in one transaction, then update `known`, delete files and warn.

    `keep_files`: dropped keys that only leave the registry (the table still exists); sent as `unregistered`, so no transport deletes their files.
    `session` deletes the folders of the dropped s3a MANAGED tables, all of them under one `S3A_DELETE_BUDGET`.
    """
    known = STATE["known"][skey]
    known_dbs = STATE.setdefault("known_dbs", {}).setdefault(skey, set())
    ignored = STATE.setdefault("ignored", {}).setdefault(skey, set())
    plan = {
        "created": created,
        "updated": [(key, known[key]["loc"], known[key]["type"], change) for key, change in updated],
        "renamed": [(old, new, known[old]["loc"], info) for old, new, info in renamed],
        "dropped": [(key, known[key]["loc"]) for key in dropped if key not in keep_files],
        "unregistered": [(key, known[key]["loc"]) for key in dropped if key in keep_files],
        "new_dbs": new_dbs,
        "gone_dbs": gone_dbs,
    }
    result = commit_plan(plan, now())
    for key, info in created:
        if key in result["adopted"]:
            known[key] = {**info, "sess_managed": info["type"] == "MANAGED"}
    for key, reason in result.get("rejected", ()):
        ignored.add(key)
        warn(("rejected", skey, key), reject_text(key, reason))
    for key in result["conflicts"]:
        ignored.add(key)
        warn(("conflict", skey, key), "table %s.%s already exists in the persistent catalog with a different location; it was not saved." % key)
    for key, change in result["updated_ok"]:
        known[key].update(change)
    for old, new, info in result["renamed_ok"]:
        rec = known.pop(old)
        known[new] = {**rec, **{f: info[f] for f in ("fmt", "loc", "cols", "parts", "dv", "hi")}}
        if rec["type"] == "MANAGED" and info["loc"] != rec["loc"] and not managed_shape(info["loc"]):
            known[new]["type"] = "EXTERNAL"  # mirrors the demotion apply_plan wrote
    for key in result["dropped_ok"]:
        known.pop(key, None)
    known_dbs |= set(new_dbs)
    known_dbs -= set(gone_dbs)
    pending = [(key, loc) for key, loc in result["deletions"] if key not in keep_files]
    for key, error in (delete_managed_s3a(session, pending) if pending else {}).items():
        if error:
            warn(("delete", skey, key), "kept the files of dropped table %s.%s (%s)." % (*key, error))
    for key in result.get("files_kept", ()):
        warn(("delete", skey, key), "kept the files of dropped table %s.%s (another registered table uses that folder, or the catalog API could not remove them)." % key)


def managed_shape(location):
    """Only `s3a://notislake/<layer>/<t>` is MANAGED; no local path is."""
    return is_s3a(location) and LOCATIONS.managed_table(location)


def deep_keys(raw_cell, known):
    """Tables to reread from Spark after a DDL cell: those it names, or all of them when it names none."""
    if not raw_cell or not DEEP_RE.search(raw_cell):
        return set()
    cited = {key for key in known if re.search(r"\b%s\b" % re.escape(key[1]), raw_cell, re.I)}
    return cited or set(known)


def confirm_vanished(session, skey, candidates):
    """Keys of `candidates` that Spark itself reports as nonexistent; a failed check keeps the table."""
    confirmed = []
    for key in candidates:
        try:
            if not session.catalog.tableExists(ident(*key)):
                confirmed.append(key)
            else:
                warn(("listing", skey, key), "table %s.%s is missing from the listing but still exists; it was kept." % key)
        except Exception as exc:
            warn(("unconfirmed", skey, key), "kept dropped-looking table %s.%s (could not confirm: %s)." % (*key, short(exc)))
    return confirmed


def reconcile(session, raw_cell):
    skey = session_key(session)
    known = STATE.get("known", {}).get(skey)
    if known is None or not session_alive(session):
        return
    ignored = STATE.setdefault("ignored", {}).setdefault(skey, set())
    known_dbs = STATE.setdefault("known_dbs", {}).setdefault(skey, set())
    dbs, current, failed = list_catalog(session)
    ignored &= set(current)
    deep = deep_keys(raw_cell, known)
    created, updated, leaving = {}, [], []
    for key, table in current.items():
        if key in known:
            if key in ignored:  # the backend rejected its last change; do not resend it every cell
                continue
            change = refresh_table(session, key, known[key], key in deep)
            if change == LEAVE:
                leaving.append(key)
            elif change:
                updated.append((key, change))
        elif key not in ignored:
            try:
                info = describe_new(session, key, table)
            except S3AUnavailable:
                continue  # undecided, not rejected: seen again in the next cell
            if info is None:
                ignored.add(key)
            else:
                created[key] = info
    # Tables of a database whose listing failed are unknown, never dropped.
    vanished = confirm_vanished(session, skey, [k for k in known if k not in current and k[0] not in failed])
    ignored.update(leaving)
    renamed = match_renames(vanished, created, known, raw_cell)
    tombstones = STATE.setdefault("tombstones", {}).setdefault(skey, set())
    tombstones &= set(dbs)
    new_dbs = {d for d in dbs if d != DEFAULT_DB and d not in LOCATIONS.LAYERS and d not in known_dbs and d not in tombstones}
    gone_dbs = {d for d in known_dbs if d not in dbs and d not in failed and d not in LOCATIONS.LAYERS}
    plan = (list(created.items()), updated, renamed, vanished + leaving, new_dbs, gone_dbs)
    if any(plan):
        apply_changes(skey, *plan, keep_files=set(leaving), session=session)


class Refused(ValueError):
    """Destination refused before anything was written; `str(exc)` is the pt-BR text the user sees."""


def refuse_text(what, code, path=False):
    reason = (REJECTED_PATH.get(code) if path else None) or REJECTED.get(code, code)
    return "Notisbook recusou %s antes de qualquer escrita (nada foi alterado): %s." % (what[:120], reason)


def split_name(text):
    """Parts of a dotted identifier (backticks quote a part); None when `text` is not one."""
    if not isinstance(text, str):
        return None
    text, parts, cur, quoted, i = text.strip(), [], [], False, 0
    while i < len(text):
        ch = text[i]
        if quoted and ch == "`" and text[i + 1:i + 2] == "`":
            cur.append(ch)
            i += 1
        elif ch == "`":
            quoted = not quoted
        elif ch == "." and not quoted:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur).strip())
    return None if quoted or not all(parts) else parts


def catalog_registered(session, name):
    return name.lower() == CATALOG or bool(conf_get(session, "spark.sql.catalog." + name.lower()))


def current_catalog(session):
    try:
        return session.catalog.currentCatalog().lower()
    except Exception:
        return None


def path_of_ident(parts):
    """The folder of a path identifier such as delta.`s3a://...`, else None."""
    if len(parts) == 2 and parts[0].lower() in FORMAT_NAMES and "/" in parts[1]:
        return parts[1]
    return None


def named_catalog(session, first):
    """True when the first part of a name is a catalog (`iceberg` counts even before its conf is read)."""
    return first.lower() == ICEBERG_CATALOG or catalog_registered(session, first)


def resolve_table(session, parts):
    """(catalog, schema, table) of a table name as Spark resolves it; None for paths, other catalogs or any doubt.

    In `iceberg` the namespace may be nested: the schema is then the dotted join (`foo.bar`), which no layer
    matches, so the destination rules refuse it. `spark_catalog` has no nested namespace.
    """
    parts = list(parts)
    if not parts or path_of_ident(parts):
        return None
    if len(parts) == 1:
        catalog = current_catalog(session)
        schema, table = session.catalog.currentDatabase(), parts[0]
    elif len(parts) == 2 and catalog_registered(session, parts[0]):
        return None  # catalog.table, no namespace to decide on
    elif len(parts) >= 3 and named_catalog(session, parts[0]):
        catalog, schema, table = parts[0].lower(), ".".join(parts[1:-1]), parts[-1]
    else:
        catalog, schema, table = current_catalog(session), ".".join(parts[:-1]), parts[-1]
    if catalog == CATALOG:
        return None if "." in schema else (catalog, schema.lower(), table.lower())  # the session catalog folds case
    return (catalog, schema, table) if catalog == ICEBERG_CATALOG else None


def resolve_namespace(session, parts):
    """(catalog, namespace) of a namespace in `spark_catalog` (one level) or `iceberg` (nested as a dotted join), else None."""
    parts = list(parts)
    if len(parts) >= 2 and catalog_registered(session, parts[0]):
        catalog, ns = parts[0].lower(), ".".join(parts[1:])
    elif parts:
        catalog, ns = current_catalog(session), ".".join(parts)
    else:
        return None
    if catalog == CATALOG:
        return None if "." in ns else (catalog, ns)
    return (catalog, ns) if catalog == ICEBERG_CATALOG else None


def iceberg_rows(conn):
    """[((namespace, table), folder or None)] of the JDBC catalog `iceberg` (folder = parent of `metadata/`)."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'iceberg_tables'").fetchone() is None:
        return []
    out = []
    for ns, name, meta in conn.execute(
            "SELECT table_namespace, table_name, metadata_location FROM iceberg_tables WHERE catalog_name = 'iceberg'"):
        parts = (meta or "").rstrip("/").split("/")[:-1]
        folder = "/".join(parts[:-1] if parts and parts[-1] == "metadata" else parts) if meta else None
        out.append(((ns, name), folder or None))
    return out


def read_known():
    """Tables of both catalogs, `{"spark": {(db, t): loc}, "iceberg": {(ns, t): loc or None}}`, keys in lower case."""
    if TRANSPORT == "http":
        data = http_call("GET", "/registry")
        spark = [((t["db"], t["name"]), t.get("loc")) for t in data["tables"]]
        lake = [((t["db"], t["name"]), t.get("loc")) for t in data.get("iceberg") or ()]
    else:
        conn = connect()
        try:
            spark = [(key, row["loc"]) for key, row in read_snapshot(conn)[1].items()]
            lake = iceberg_rows(conn)
        finally:
            conn.close()
    return {name: {(k[0].lower(), k[1].lower()): loc for k, loc in items} for name, items in (("spark", spark), ("iceberg", lake))}


def known_view(session):
    """`read_known` minus the tables this cell dropped plus what it already created; None when the registry is unreadable."""
    try:
        view = read_known()
    except Exception:
        warn(("known", session_key(session)), "não foi possível ler o catálogo persistente; sobreposição entre tabelas e nome repetido só serão checados depois da gravação.")
        return None
    skey = session_key(session)
    for catalog, key in list(STATE.get("dropped", {}).get(skey, ())):
        view["spark" if catalog == CATALOG else "iceberg"].pop(key, None)  # o registro só muda no post_run_cell
    for (catalog, key), loc in list(STATE.get("intent", {}).get(skey, {}).items()):
        view["spark" if catalog == CATALOG else "iceberg"][key] = loc
    return view


def lake_locations(view, skip=None):
    """Folders of every known table of both catalogs, except the one named `skip` = (catalog, key)."""
    if view is None:
        return []
    return [loc for name, rows in view.items() for key, loc in rows.items()
            if loc and skip != (CATALOG if name == "spark" else ICEBERG_CATALOG, key)]


def add_pending(entry):
    """Queue an effect on the innermost wrapped call of this thread; outside one there is nothing to commit."""
    stack = getattr(PENDING, "stack", None)
    if stack:
        stack[-1].append(entry)


def check_table(session, catalog, schema, table, location):
    """Raise Refused when creating `schema.table` (location None: the managed folder) breaks the destination rules.

    The same name in the other catalog is refused for any location; the layer rules only apply to what lands in the notislake:
    an explicit s3/s3a/s3n location there, a managed table of a layer, or any managed `iceberg` table (its
    warehouse is the bucket root). Other destinations (local disk, other buckets) are left to Spark.
    Without a location, a table already registered keeps its own folder and is not checked as a new destination.
    """
    key, label = (schema.lower(), table.lower()), "criar a tabela %s.%s" % (schema, table)
    view = known_view(session)
    mine, other = ("spark", "iceberg") if catalog == CATALOG else ("iceberg", "spark")
    if view is not None and key not in view[mine] and key in view[other]:
        raise Refused(refuse_text(label, "name_in_other_catalog" if catalog == CATALOG else "name_in_spark_catalog"))
    on_lake = location is not None and LOCATIONS.targets_notislake(location)
    if catalog == ICEBERG_CATALOG and (location is None or on_lake) and LOCATIONS.is_layer_case_variant(schema):
        raise Refused(refuse_text(label, "schema_not_layer"))  # o JdbcCatalog gravaria em `<raiz>/Bronze/`, fora das camadas
    if not on_lake and (location is not None or (catalog == CATALOG and LOCATIONS.layer_of_schema(schema) is None)):
        return
    if location is None and view is not None and key in view[mine]:
        return  # a write to a registered table (append, IF NOT EXISTS, replace) keeps its folder: no destination to compute nor to record
    try:
        effective = LOCATIONS.table_destination(schema, table, location, lake_locations(view, (catalog, key)))
    except LOCATIONS.InvalidLocation as exc:
        raise Refused(refuse_text(label, exc.code)) from None
    add_pending((session_key(session), "intent", catalog, key, effective))


def note_drop(session, parts):
    """DROP TABLE: once it succeeds, the table leaves this cell's view of the destinations."""
    target = resolve_table(session, parts)
    if target is not None:
        add_pending((session_key(session), "drop", target[0], (target[1], target[2]), None))


def commit_pending(pending):
    """Make the effects of a statement that returned without error visible to the next checks of the cell."""
    for skey, kind, catalog, key, loc in pending:
        intent = STATE.setdefault("intent", {}).setdefault(skey, {})
        if kind == "drop":
            STATE.setdefault("dropped", {}).setdefault(skey, set()).add((catalog, key))
            intent.pop((catalog, key), None)
        else:
            intent[(catalog, key)] = loc


def check_path(session, path):
    """Raise Refused for a path write into the notislake that the path rules forbid (a table's own folder is allowed)."""
    if not isinstance(path, str) or not LOCATIONS.targets_notislake(path):
        return
    view = known_view(session)
    own = None
    if view is not None:
        wanted = notislake_uri(path)
        own = next((loc for loc in view["spark"].values() if wanted and notislake_uri(loc or "") == wanted), None)
    try:
        LOCATIONS.check_path_write(path, lake_locations(view), own)
    except LOCATIONS.InvalidLocation as exc:
        raise Refused(refuse_text("gravar em %s" % path, exc.code, path=True)) from None


def layer_exists(session, layer):
    """True when `spark_catalog` already lists the layer (the hook's own query, so it skips the checks)."""
    with Bypass():
        rows = session.sql("SHOW NAMESPACES IN " + CATALOG).collect()
    return layer in {str(row[0]).lower() for row in rows}


def check_namespace(kind, session, parts, location=None, if_not_exists=False):
    """Layers are never dropped nor moved; a schema that is not a layer never points into the notislake.

    `CREATE ... IF NOT EXISTS <layer>` without LOCATION is a no-op on an existing layer and is not refused.
    """
    target = resolve_namespace(session, parts)
    if target is None:
        return
    ns = target[1]
    iceberg = target[0] == ICEBERG_CATALOG
    layer = (ns if ns in LOCATIONS.LAYERS else None) if iceberg else LOCATIONS.layer_of_schema(ns)  # Iceberg keeps the case
    if kind == "create" and iceberg and LOCATIONS.is_layer_case_variant(ns):
        raise Refused(refuse_text("criar o schema " + ns, "schema_not_layer"))
    label = {"drop": "remover o schema", "create": "criar o schema", "set": "mudar a location do schema"}[kind] + " " + ns
    if layer:
        # A layer made in `spark_catalog` without its LOCATION would be born in the local warehouse.
        unplaced = kind == "create" and not iceberg and location is None and not (if_not_exists and layer_exists(session, layer))
        moved = unplaced or (location is not None and location.rstrip("/") != LOCATIONS.layer_uri(layer))
        if kind == "drop" or kind == "set" or moved:
            raise Refused(refuse_text(label, "layer_protected"))
    elif kind != "drop" and location and LOCATIONS.targets_notislake(location):
        raise Refused(refuse_text(label, "schema_not_layer"))


def check_table_location(session, parts, location):
    """ALTER TABLE ... SET LOCATION: a destination in the notislake must pass the same rules as a new table."""
    target = resolve_table(session, parts)
    if target is None or not LOCATIONS.targets_notislake(location):
        return
    catalog, schema, table = target
    view = known_view(session)
    label = "mudar a location de %s.%s" % (schema, table)
    try:
        LOCATIONS.table_destination(schema, table, location, lake_locations(view, (catalog, (schema.lower(), table.lower()))))
    except LOCATIONS.InvalidLocation as exc:
        raise Refused(refuse_text(label, exc.code)) from None


def check_rename(session, parts, new_name):
    """ALTER TABLE ... RENAME TO on `iceberg`: the folder stays, so the new name must still fit its layer and be free in `spark_catalog`.

    Local `iceberg` (JDBC) writes `catalog.db` directly, with no REST in between. A `spark_catalog` rename is left
    to `apply_plan` (the session catalog does not move a table across schemas).
    """
    target = resolve_table(session, parts)
    if target is None or target[0] != ICEBERG_CATALOG or not new_name:
        return
    view = known_view(session)
    old_key = (target[1].lower(), target[2].lower())
    if view is None or old_key not in view["iceberg"]:
        return
    new_schema, new_table = ".".join(new_name[:-1]) or target[1], new_name[-1]  # a bare name stays in the table's namespace
    label = "renomear a tabela %s.%s" % (target[1], target[2])
    if (new_schema.lower(), new_table.lower()) in view["spark"]:
        raise Refused(refuse_text(label, "name_in_spark_catalog"))
    current = view["iceberg"][old_key]
    if current and LOCATIONS.targets_notislake(current):
        try:
            LOCATIONS.table_destination(new_schema, new_table, current, lake_locations(view, (ICEBERG_CATALOG, old_key)))
        except LOCATIONS.InvalidLocation as exc:
            raise Refused(refuse_text(label, exc.code)) from None


def table_statement(session, parts, location):
    path = path_of_ident(parts)
    if path:
        check_path(session, path)
        return
    target = resolve_table(session, parts)
    if target is not None:
        check_table(session, *target, location)


def jtype(obj):
    getter = getattr(obj, "getClass", None)  # py4j objects only; str/bool/None have no such attribute
    return getter().getSimpleName() if callable(getter) else type(obj).__name__


def jseq(seq):
    return [seq.apply(i) for i in range(seq.size())]


def jopt(opt):
    return opt.get() if opt.isDefined() else None


def identifier_parts(tid):
    """Parts of a catalyst TableIdentifier (catalog, database, table), skipping the absent ones."""
    return [str(v) for v in (jopt(tid.catalog()), jopt(tid.database()), tid.table()) if v is not None]


def check_plan(session, plan):
    """Run the destination rules on the parsed statement (node shapes verified on Spark 3.5.4 and 3.5.9)."""
    kind = jtype(plan)
    items = [plan.productElement(i) for i in range(plan.productArity())]
    named = {}
    for item in items:
        named.setdefault(jtype(item), item)
    if kind in TABLE_NODES:
        ident, spec = named.get("UnresolvedIdentifier"), named.get("UnresolvedTableSpec")
        if ident is not None and spec is not None:
            table_statement(session, jseq(ident.nameParts()), jopt(spec.location()))
    elif kind == "CreateTableLikeCommand":
        storage = named.get("CatalogStorageFormat")
        location = jopt(storage.locationUri()) if storage is not None else None
        table_statement(session, identifier_parts(items[0]), None if location is None else str(location))
    elif kind == "InsertIntoStatement":
        relation = named.get("UnresolvedRelation")
        path = path_of_ident(jseq(relation.multipartIdentifier())) if relation is not None else None
        if path:
            check_path(session, path)
    elif kind == "InsertIntoDir":
        location = jopt(named["CatalogStorageFormat"].locationUri())
        if location is not None:
            check_path(session, str(location))
    elif kind == "RenameTable" and items[2] is False and "UnresolvedTableOrView" in named:
        check_rename(session, jseq(named["UnresolvedTableOrView"].multipartIdentifier()), jseq(items[1]))
    elif kind == "DropTable" and "UnresolvedIdentifier" in named:
        note_drop(session, jseq(named["UnresolvedIdentifier"].nameParts()))
    elif kind == "DropNamespace":
        check_namespace("drop", session, jseq(named["UnresolvedNamespace"].multipartIdentifier()))
    elif kind == "CreateNamespace":
        check_namespace("create", session, jseq(named["UnresolvedNamespace"].multipartIdentifier()), jopt(items[2].get("location")), items[1] is True)
    elif kind == "SetNamespaceLocation":
        check_namespace("set", session, jseq(named["UnresolvedNamespace"].multipartIdentifier()), items[1])
    elif kind == "SetTableLocation":
        check_table_location(session, jseq(named["UnresolvedTable"].multipartIdentifier()), next(i for i in items if isinstance(i, str)))


def checks_on(session):
    """The checks apply to an attached session, never to the hook's own calls."""
    if session is None or getattr(BYPASS, "depth", 0):
        return False
    try:
        skey = session_key(session)
    except Exception:
        return False
    return skey in STATE.get("attached", ()) and skey not in STATE.get("off", ())


def precheck(fn, *args):
    """Run a check; only `Refused` reaches the user. Any other failure lets the call go on (post-write validation still runs).

    Fail-safe on purpose: a statement the parser or the introspection cannot read must not be blocked
    in an opaque way; only a destination proven invalid is refused.
    """
    try:
        fn(*args)
    except Refused:
        raise
    except Exception as exc:
        errors = STATE.setdefault("errors", [])
        errors.append("precheck %s: %s" % (fn.__name__, type(exc).__name__))
        del errors[:-MAX_ERRORS]
        warn(("precheck", fn.__name__), "a checagem prévia do destino não pôde ser feita; a gravação segue e a validação posterior continua valendo.")


def sql_text(args, kwargs):
    text = args[0] if args else kwargs.get("sqlQuery")
    if not isinstance(text, str):
        return None
    fields = {k: v for k, v in kwargs.items() if k not in ("sqlQuery", "args")}
    if fields:
        if not all(isinstance(v, (str, int, float)) for v in fields.values()):
            return None
        try:
            text = text.format(**fields)
        except (KeyError, IndexError, ValueError):
            return None
    return text


def before_sql(session, args, kwargs):
    text = sql_text(args, kwargs)
    if text is None or not STATEMENT_RE.search(text) or not checks_on(session):
        return
    try:
        plan = session._jsparkSession.sessionState().sqlParser().parsePlan(text)
    except Exception:
        return  # Spark reports its own syntax error
    check_plan(session, plan)


def writer_session(writer):
    session = getattr(writer, "_spark", None) or current_session()
    return session if checks_on(session) else None


def record_of(obj):
    return obj.__dict__.setdefault("_notisbook", {"opts": {}, "props": {}})


def arg_of(args, kwargs, index, name):
    return args[index] if len(args) > index else kwargs.get(name)


def before_path_write(writer, args, kwargs):
    session = writer_session(writer)
    if session is None:
        return
    path = arg_of(args, kwargs, 0, "path")
    check_path(session, path if path is not None else record_of(writer)["opts"].get("path"))


def before_save_as_table(writer, args, kwargs):
    session = writer_session(writer)
    parts = split_name(arg_of(args, kwargs, 0, "name")) if session is not None else None
    target = resolve_table(session, parts) if parts else None
    if target is not None:
        path = kwargs.get("path", record_of(writer)["opts"].get("path"))
        check_table(session, *target, None if path is None else str(path))


def before_create_v2(writer, args, kwargs):
    session = writer_session(writer)
    rec = record_of(writer)
    parts = split_name(rec.get("table")) if session is not None else None
    target = resolve_table(session, parts) if parts else None
    if target is None:
        return
    # Spike (Spark 3.5.9 and Glue 3.5.4): both Delta and Iceberg honour only `option("path")` and
    # `tableProperty("location")`; `option("location")` and `tableProperty("path")` are ignored in silence.
    locations = [v for v in (rec["opts"].get("path"), rec["props"].get("location")) if v is not None]
    for location in locations or [None]:
        check_table(session, *target, str(location) if location is not None else None)


def before_create_table(catalog, args, kwargs):
    session = getattr(catalog, "_sparkSession", None) or current_session()
    parts = split_name(arg_of(args, kwargs, 0, "tableName")) if checks_on(session) else None
    target = resolve_table(session, parts) if parts else None
    if target is not None:
        path = arg_of(args, kwargs, 1, "path")
        path = kwargs.get("path", path) if path is None else path
        check_table(session, *target, None if path is None else str(path))


def wrap_checked(original, before):
    @functools.wraps(original)
    def method(self, *args, **kwargs):
        pending = []
        try:
            stack = PENDING.stack = getattr(PENDING, "stack", None) or []
            stack.append(pending)  # per thread and per call: a nested wrapped call gets its own list
        except Exception:
            stack = None
        try:
            precheck(before, self, args, kwargs)
        finally:
            if stack:
                stack.pop()
        result = original(self, *args, **kwargs)
        guarded("commit_pending", commit_pending, pending)  # only a statement that returned without error counts for the next checks
        return result
    method._notisbook_original = original
    return method


def wrap_recorded(original, record):
    @functools.wraps(original)
    def method(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        try:
            record(self, args, kwargs)
        except Exception:
            pass  # a missed record only means a missed pre-check
        return result
    method._notisbook_original = original
    return method


def record_format(writer, args, kwargs):
    record_of(writer)["format"] = arg_of(args, kwargs, 0, "source") or arg_of(args, kwargs, 0, "provider")


def record_option(writer, args, kwargs):
    record_of(writer)["opts"][str(arg_of(args, kwargs, 0, "key")).lower()] = arg_of(args, kwargs, 1, "value")


def record_options(writer, args, kwargs):
    record_of(writer)["opts"].update({str(k).lower(): v for k, v in kwargs.items()})


def record_property(writer, args, kwargs):
    record_of(writer)["props"][str(arg_of(args, kwargs, 0, "property")).lower()] = arg_of(args, kwargs, 1, "value")


def record_table(writer, args, kwargs):
    record_of(writer)["table"] = arg_of(args, kwargs, 1, "table")


def intercepts():
    """`{class name: [(method, wrapper factory)]}`: where each pre-write check hangs."""
    def checked(before):
        return lambda original: wrap_checked(original, before)

    def recorded(record):
        return lambda original: wrap_recorded(original, record)

    writer = [("format", recorded(record_format)), ("option", recorded(record_option)), ("options", recorded(record_options)),
              ("save", checked(before_path_write)), ("saveAsTable", checked(before_save_as_table))]
    writer += [(name, checked(before_path_write)) for name in ("parquet", "json", "csv", "orc", "text")]
    return {
        "DataFrameWriter": writer,
        "DataFrameWriterV2": [("__init__", recorded(record_table)), ("using", recorded(record_format)),
                              ("option", recorded(record_option)), ("options", recorded(record_options)),
                              ("tableProperty", recorded(record_property))]
                             + [(name, checked(before_create_v2)) for name in ("create", "createOrReplace", "replace")],
        "Catalog": [("createTable", checked(before_create_table))],
        "SparkSession": [("sql", checked(before_sql))],
    }


def unwrap(func):
    while hasattr(func, "_notisbook_original"):
        func = func._notisbook_original
    return func


def wrap_get_or_create(original):
    @functools.wraps(original)
    def get_or_create(self):
        session = original(self)
        guarded("getOrCreate", attach, session)
        return session
    get_or_create._notisbook_original = original
    return get_or_create


def wrap_stop(original):
    @functools.wraps(original)
    def stop(self):
        def before_stop():
            if getattr(self, "_jsparkSession", None) is not None:
                reconcile(self, None)
                STATE.get("attached", set()).discard(session_key(self))
                STATE.get("s3a_done", set()).discard(session_key(self))
                for table in ("known", "known_dbs", "ignored", "tombstones", "s3a_status", "s3a_fs", "layers_checked", "intent", "dropped"):
                    STATE.get(table, {}).pop(session_key(self), None)
        if session_alive(self):
            guarded("stop", before_stop)
        return original(self)
    stop._notisbook_original = original
    return stop


def patch(module):
    """Wrap, in the classes `module` defines, the session lifecycle and the pre-write checks; `unwrap` first, so never twice."""
    cls = getattr(module, "SparkSession", None)
    if cls is not None:
        builder = getattr(cls, "Builder", None)
        if builder is not None and "getOrCreate" in vars(builder):
            builder.getOrCreate = wrap_get_or_create(unwrap(vars(builder)["getOrCreate"]))
        if "stop" in vars(cls):
            cls.stop = wrap_stop(unwrap(vars(cls)["stop"]))
    for name, specs in intercepts().items():
        target = getattr(module, name, None)
        for method, factory in specs if isinstance(target, type) else ():
            if method in vars(target):
                setattr(target, method, factory(unwrap(vars(target)[method])))


class Finder(importlib.abc.MetaPathFinder):
    _notisbook_finder = True

    def find_spec(self, name, path, target=None):
        if name not in WATCHED or name in BUSY:
            return None
        BUSY.add(name)
        try:
            spec = importlib.util.find_spec(name)
        except Exception:
            return None
        finally:
            BUSY.discard(name)
        loader = getattr(spec, "loader", None)
        if loader is None or not hasattr(loader, "exec_module"):
            return spec
        original_exec = loader.exec_module

        def exec_module(module):
            original_exec(module)
            guarded("patch", patch, module)
        loader.exec_module = exec_module
        return spec


def cell_session(attach_if_needed):
    session = current_session()
    if session is None:
        return None, None
    skey = session_key(session)
    if skey in STATE.setdefault("off", set()):
        return None, None
    if skey not in STATE.setdefault("attached", set()):
        if not attach_if_needed:
            return None, None
        attach(session)
        if skey not in STATE["attached"]:
            return None, None
    return session, skey


def _pre():
    session, skey = cell_session(True)
    if session is not None:
        sync_registry(session, skey)


def _post(result):
    session, skey = cell_session(True)
    if session is not None:
        for table in ("intent", "dropped"):
            STATE.get(table, {}).pop(skey, None)  # the cell is over: its creations and drops are in the session catalog now
        info = getattr(result, "info", None)
        reconcile(session, getattr(info, "raw_cell", None))


def on_pre(info=None):
    guarded("pre_run_cell", _pre)


def on_post(result=None):
    guarded("post_run_cell", _post, result)


def register():
    sys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, "_notisbook_finder", False)]
    sys.meta_path.insert(0, Finder())
    for name in WATCHED:
        module = sys.modules.get(name)
        if module is not None:
            guarded("patch", patch, module)
    from IPython import get_ipython
    ip = get_ipython()
    if ip is None:
        return
    for event, callback in STATE.pop("callbacks", []):
        try:
            ip.events.unregister(event, callback)
        except ValueError:
            pass
    STATE["callbacks"] = [("pre_run_cell", on_pre), ("post_run_cell", on_post)]
    for event, callback in STATE["callbacks"]:
        ip.events.register(event, callback)
'''

# Same install pattern as `sql_cell`: exec in a throwaway dict, reinstall only when the version
# differs (STATE, e.g. the known tables, is carried to the new module), `register` always runs.
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
mod.register()
'''


def _render(config: dict[str, object]) -> str:
    locations_source = inspect.getsource(notislake_locations)
    helpers = "\n\n\n".join(inspect.getsource(fn).rstrip() for fn in (read_snapshot, apply_plan))
    config = {**config, "s3a_closed": closed_options()}
    source = (
        _KERNEL_TEMPLATE.replace("__REGISTRY_HELPERS__", helpers)
        .replace("__LOCATIONS_SOURCE__", repr(locations_source))
        .replace("__CONFIG__", repr(json.dumps(config)))
    )
    version = hashlib.sha1(source.encode()).hexdigest()[:12]
    ensure = (
        _ENSURE_TEMPLATE.replace("__MODULE__", repr(MODULE_NAME))
        .replace("__VERSION__", repr(version))
        .replace("__SOURCE__", repr(source))
    )
    return f"exec({ensure!r}, {{}})"


def _with_s3a(config: dict[str, object], s3a: Mapping[str, str] | None) -> dict[str, object]:
    """Add the resolved `fs.s3a.bucket.notislake.*` options to the config; the secret lives only in the snippet literal."""
    return {**config, "s3a": dict(s3a)} if s3a else config


def build_ensure_code(db_path: str, s3a: Mapping[str, str] | None = None) -> str:
    """Return the idempotent snippet that installs the catalog hook with the given catalog path (SQLite transport)."""
    return _render(_with_s3a({"db_path": db_path}, s3a))


def build_http_ensure_code(
    base_url: str,
    token: str,
    roots: tuple[str, ...],
    s3a: Mapping[str, str] | None = None,
) -> str:
    """Snippet for the Docker runtime: the hook talks to the backend API with the session token, never to SQLite.

    The token travels only in the JSON literal of this code (not in env vars nor in the Spark submit args).
    """
    config = {
        "transport": "http",
        "base_url": base_url,
        "token": token,
        "roots": list(roots),
    }
    return _render(_with_s3a(config, s3a))
