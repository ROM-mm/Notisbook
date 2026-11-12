"""Hidden kernel module `_notisbook_catalog`: keeps the SparkSession in sync with `catalog.db`.

Installed by the same silent execute as the renderer. It hooks `SparkSession.Builder.getOrCreate`
and `SparkSession.stop` through a `sys.meta_path` finder (no pyspark import by the module itself),
hydrates the session from the `nb_*` registry inside `getOrCreate`, reconciles creations, changes,
renames and drops after every cell (`post_run_cell`) and picks up other kernels' writes before a
cell (`pre_run_cell`, by `nb_meta.generation`). Only Delta/Parquet/Hudi tables of `spark_catalog` are
registered (Hudi advances are detected by the latest completed timeline instant); the backend owns
the schema and Iceberg lives in its own JDBC catalog.

The config reaches the kernel as JSON literals (the kernel reads no env vars). Hook errors never
reach the user's cell: they are kept in `STATE["errors"]` and warned once, briefly, on stderr.
Files of a dropped MANAGED table are deleted only under `managed_root` (see `delete_managed`).
"""

import hashlib
import inspect
import json

from ..catalog.managed import managed_table_dir

MODULE_NAME = "_notisbook_catalog"

# Plain string (not an f-string); `build_ensure_code` substitutes __CONFIG__ and __MANAGED_HELPERS__.
_KERNEL_TEMPLATE = r'''
import functools, importlib.abc, importlib.util, json, os, re, shutil, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

CONFIG = json.loads(__CONFIG__)
DB_PATH = CONFIG["db_path"]
MANAGED_ROOT = CONFIG["managed_root"]
ICEBERG_WAREHOUSE = CONFIG["iceberg_warehouse"]
WATCHED = ("pyspark.sql.session", "pyspark.sql.classic.session")
SUPPORTED = ("delta", "parquet", "hudi")
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


def guarded(where, fn, *args):
    # A hook failure must never surface in the user's cell.
    try:
        return fn(*args)
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


def norm_loc(location):
    # Same form the backend's Iceberg reader returns (`Path.as_uri()`): one location format in the API.
    path = local_path(location)
    return Path(path).as_uri() if path else location


def is_under(location, root):
    """True when `location` is `root` or inside it (compared with a trailing separator: `a/iceberg` is not `a/iceberg_raw`)."""
    return (location.rstrip("/") + "/").startswith(root.rstrip("/") + "/")


def delta_versions(location):
    base = local_path(location)
    if not base:
        return []
    try:
        names = os.listdir(os.path.join(base, "_delta_log"))
    except OSError:
        return []
    return [int(m.group(1)) for m in map(LOG_RE.match, names) if m]


def delta_version(location):
    versions = delta_versions(location)
    return max(versions) if versions else None


def delta_advanced(location, version):
    base = local_path(location)
    if not base:
        return False
    if version is None:
        return delta_version(location) is not None
    return os.path.exists(os.path.join(base, "_delta_log", "%020d.json" % (version + 1)))


def hudi_instant(location):
    """Marker of the latest completed Hudi instant, or None (`.requested`/`.inflight` and dotfiles never match).

    Layout v2 (`.hoodie/timeline/<req>_<comp>.<action>`): ordered by completion time, so a commit that finishes
    out of order still moves the marker; returns `<req>_<comp>`. Layout v1 (no `timeline/` folder, Hudi 0.x):
    `.hoodie/<ts>.<action>`, returns `<ts>`.
    """
    base = local_path(location)
    if not base:
        return None
    hoodie = os.path.join(base, ".hoodie")
    try:
        names = os.listdir(os.path.join(hoodie, "timeline"))
    except FileNotFoundError:
        try:
            names = os.listdir(hoodie)
        except OSError:
            return None
        legacy = [m.group(1) for m in map(HUDI_V1_INSTANT_RE.match, names) if m]
        return max(legacy, key=int) if legacy else None
    except OSError:
        return None
    done = [m.groups() for m in map(HUDI_INSTANT_RE.match, names) if m]
    if not done:
        return None
    req, comp = max(done, key=lambda g: (int(g[1]), int(g[0])))
    return "%s_%s" % (req, comp)


__MANAGED_HELPERS__


def delete_managed(location):
    """Delete a dropped MANAGED table folder; returns an error text, or None when deleted/nothing to do.

    Safeguards: real path inside `managed_root` and shaped like `<root>/<t>` or `<root>/<db>.db/<t>`
    (never the root nor a `*.db` folder), and it must be an existing directory.
    """
    path = local_path(location)
    if not path:
        return "location is not a local path"
    real, error = managed_table_dir(path, MANAGED_ROOT)
    if error:
        return error
    if not os.path.isdir(real):
        return None
    try:
        shutil.rmtree(real)
    except OSError as exc:
        return short(exc)
    return None


def connect():
    # mode=rw: the backend creates catalog.db; a missing file must not become an empty database.
    conn = sqlite3.connect("file:%s?mode=rw" % quote(DB_PATH), uri=True, isolation_level=None, timeout=10.0)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def read_generation(conn):
    row = conn.execute("SELECT value FROM nb_meta WHERE key = 'generation'").fetchone()
    return int(row[0]) if row else 0


def read_registry():
    conn = connect()
    try:
        gen = read_generation(conn)
        rows = {}
        for db, name, fmt, loc, typ, cols, parts, dv, hi in conn.execute(
            "SELECT namespace, table_name, format, location, table_type, columns_json, partition_cols, delta_version, "
            "hudi_instant "
            "FROM nb_tables WHERE catalog_name = 'spark_catalog'"
        ):
            rows[(db, name)] = {"fmt": fmt, "loc": loc, "type": typ, "cols": json.loads(cols),
                                "parts": json.loads(parts), "dv": dv, "hi": hi}
        namespaces = {r[0] for r in conn.execute("SELECT namespace FROM nb_namespaces WHERE catalog_name = 'spark_catalog'")}
    finally:
        conn.close()
    return gen, rows, namespaces


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
    if is_under(loc, norm_loc(ICEBERG_WAREHOUSE)):
        return None
    fmt = info["provider"]
    parts = [c["name"] for c in info["columns"] if c["is_partition"]]
    return {"fmt": fmt, "loc": loc, "type": table.tableType, "cols": info["columns"], "parts": parts,
            "dv": delta_version(loc) if fmt == "delta" else None,
            "hi": hudi_instant(loc) if fmt == "hudi" else None, "description": table.description}


def hydrate(session, skey, rows, namespaces, listing=None):
    """Create in the session the registry tables it lacks; returns the registry keys it skipped."""
    known = STATE.setdefault("known", {}).setdefault(skey, {})
    known_dbs = STATE.setdefault("known_dbs", {}).setdefault(skey, set())
    dbs, current, _ = listing or list_catalog(session)
    for ns in sorted(namespaces - {DEFAULT_DB}):
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
    changes = []
    for key in keys:
        change = refresh_table(session, key, known[key], deep=known[key]["fmt"] == "parquet")
        if change:
            changes.append((key, change))
    if changes:
        apply_changes(skey, [], changes, [], [], set(), set())


def attach(session):
    if getattr(session, "_jsparkSession", None) is None:
        return
    skey = session_key(session)
    if skey in STATE.setdefault("attached", set()) or skey in STATE.setdefault("off", set()):
        return
    if conf_get(session, "spark.sql.catalogImplementation") == "hive":
        STATE["off"].add(skey)
        warn(("hive", skey), "Hive support is active; the persistent catalog is off for this session.")
        return
    if conf_get(session, "spark.sql.catalog.iceberg") and conf_get(session, "spark.sql.catalog.iceberg.type") != "jdbc":
        warn(("outdated", skey), OUTDATED % session.version)
    gen, rows, namespaces = read_registry()
    refresh = hydrate(session, skey, rows, namespaces | {k[0] for k in rows})
    STATE["gen"] = gen
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


def sync_registry(session, skey):
    """Before a cell: bring in what other kernels registered or dropped since the last look."""
    conn = connect()
    try:
        if read_generation(conn) == STATE.get("gen"):
            return
    finally:
        conn.close()
    gen, rows, namespaces = read_registry()
    # Without a reliable spark_catalog listing nothing is dropped or hydrated in this cell.
    listing = list_catalog(session)
    known = STATE["known"].setdefault(skey, {})
    for key, rec in list(known.items()):
        if key in rows:
            continue
        # A table this session created as MANAGED would take its files with it on DROP: keep it while they exist.
        path = local_path(rec["loc"])
        if not (rec.get("sess_managed") and path and os.path.exists(path)):
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
    STATE["gen"] = gen
    guarded("refresh", refresh_hydrated, session, skey, refresh)


def refresh_table(session, key, rec, deep):
    """Changed fields of a known table, or None. `deep` rereads location/format/schema from Spark."""
    fmt, loc, cols, parts, dv = rec["fmt"], rec["loc"], rec["cols"], rec["parts"], rec["dv"]
    hi = rec.get("hi")  # absent in records carried over from a hook version that predates Hudi
    if deep:
        info = read_info(session, *key)
        if info["provider"] in SUPPORTED:
            fmt, loc, cols = info["provider"], norm_loc(info["location"]), info["columns"]
            parts = [c["name"] for c in cols if c["is_partition"]]
    if fmt == "delta" and (deep or delta_advanced(loc, dv)):
        cols = table_columns(session, key, parts)
        dv = delta_version(loc)
    cur = hudi_instant(loc) if fmt == "hudi" else None  # read before the schema: a commit in between is seen next time
    if fmt == "hudi" and (deep or cur != hi):
        cols = table_columns(session, key, parts)
        hi = cur
    new = {"fmt": fmt, "loc": loc, "cols": cols, "parts": parts, "dv": dv, "hi": hi}
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


def apply_changes(skey, created, updated, renamed, dropped, new_dbs, gone_dbs):
    """Write the plan in one transaction, then update `known`, delete files and warn."""
    known = STATE["known"][skey]
    known_dbs = STATE.setdefault("known_dbs", {}).setdefault(skey, set())
    ignored = STATE.setdefault("ignored", {}).setdefault(skey, set())
    adopted, conflicts, deletions = [], [], []
    stamp = now()
    dropped_ok, renamed_ok, updated_ok = [], [], []

    def row_of(conn, key):
        return conn.execute(
            "SELECT location, table_type FROM nb_tables WHERE catalog_name = 'spark_catalog' "
            "AND namespace = ? AND table_name = ?", key).fetchone()

    def fn(conn):
        changed = False
        for key, info in created:
            row = row_of(conn, key)
            if row is None:
                conn.execute(
                    "INSERT INTO nb_tables (catalog_name, namespace, table_name, format, location, table_type, "
                    "columns_json, partition_cols, options_json, delta_version, hudi_instant, description, created_at, updated_at) "
                    "VALUES ('spark_catalog', ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, ?, ?)",
                    (*key, info["fmt"], info["loc"], info["type"], json.dumps(info["cols"]), json.dumps(info["parts"]),
                     info["dv"], info["hi"], info.get("description"), stamp, stamp))
                changed = True
                adopted.append(key)
            elif row[0] == info["loc"]:
                adopted.append(key)
            else:
                conflicts.append(key)
        for key, change in updated:
            rec = known[key]
            typ = rec["type"]
            if typ == "MANAGED" and change["loc"] != rec["loc"] and not managed_shape(change["loc"]):
                typ = "EXTERNAL"
            cur = conn.execute(
                "UPDATE nb_tables SET format = ?, location = ?, table_type = ?, columns_json = ?, partition_cols = ?, "
                "delta_version = ?, hudi_instant = ?, updated_at = ? WHERE catalog_name = 'spark_catalog' "
                "AND namespace = ? AND table_name = ? AND location = ?",
                (change["fmt"], change["loc"], typ, json.dumps(change["cols"]), json.dumps(change["parts"]),
                 change["dv"], change["hi"], stamp, *key, rec["loc"]))
            if cur.rowcount:
                changed = True
                updated_ok.append((key, {**change, "type": typ}))
        for old, new, info in renamed:
            rec = known[old]
            try:
                cur = conn.execute(
                    "UPDATE nb_tables SET namespace = ?, table_name = ?, format = ?, location = ?, columns_json = ?, "
                    "partition_cols = ?, delta_version = ?, hudi_instant = ?, updated_at = ? WHERE catalog_name = 'spark_catalog' "
                    "AND namespace = ? AND table_name = ? AND location = ?",
                    (*new, info["fmt"], info["loc"], json.dumps(info["cols"]), json.dumps(info["parts"]), info["dv"],
                     info["hi"], stamp, *old, rec["loc"]))
            except sqlite3.IntegrityError:
                conflicts.append(new)
                continue
            if cur.rowcount:
                changed = True
                renamed_ok.append((old, new, info))
        for key in dropped:
            row, rec = row_of(conn, key), known[key]
            dropped_ok.append(key)
            if row is None or row[0] != rec["loc"]:
                continue  # another kernel already dropped or recreated it
            conn.execute(
                "DELETE FROM nb_tables WHERE catalog_name = 'spark_catalog' AND namespace = ? AND table_name = ?", key)
            changed = True
            shared = conn.execute("SELECT count(*) FROM nb_tables WHERE location = ?", (row[0],)).fetchone()[0]
            if row[1] == "MANAGED" and not shared:
                deletions.append((key, row[0]))
        for ns in new_dbs:
            changed |= conn.execute(
                "INSERT OR IGNORE INTO nb_namespaces (catalog_name, namespace, location, created_at) "
                "VALUES ('spark_catalog', ?, NULL, ?)", (ns, stamp)).rowcount > 0
        for ns in gone_dbs:
            left = conn.execute(
                "SELECT count(*) FROM nb_tables WHERE catalog_name = 'spark_catalog' AND namespace = ?", (ns,)).fetchone()[0]
            if not left:
                changed |= conn.execute(
                    "DELETE FROM nb_namespaces WHERE catalog_name = 'spark_catalog' AND namespace = ?", (ns,)).rowcount > 0
        return changed

    write_txn(fn)
    for key, info in created:
        if key in adopted:
            known[key] = {**info, "sess_managed": info["type"] == "MANAGED"}
    for key in conflicts:
        ignored.add(key)
        warn(("conflict", skey, key), "table %s.%s already exists in the persistent catalog with a different location; it was not saved." % key)
    for key, change in updated_ok:
        known[key].update(change)
    for old, new, info in renamed_ok:
        rec = known.pop(old)
        known[new] = {**rec, **{f: info[f] for f in ("fmt", "loc", "cols", "parts", "dv", "hi")}}
    for key in dropped_ok:
        known.pop(key, None)
    known_dbs |= set(new_dbs)
    known_dbs -= set(gone_dbs)
    for key, loc in deletions:
        error = delete_managed(loc)
        if error:
            warn(("delete", skey, key), "kept the files of dropped table %s.%s (%s)." % (*key, error))


def managed_shape(location):
    path = local_path(location)
    if not path:
        return False
    real, root = os.path.realpath(path), os.path.realpath(MANAGED_ROOT)
    return real.startswith(root + os.sep) and len(os.path.relpath(real, root).split(os.sep)) <= 2


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
    created, updated = {}, []
    for key, table in current.items():
        if key in known:
            change = refresh_table(session, key, known[key], key in deep)
            if change:
                updated.append((key, change))
        elif key not in ignored:
            info = describe_new(session, key, table)
            if info is None:
                ignored.add(key)
            else:
                created[key] = info
    # Tables of a database whose listing failed are unknown, never dropped.
    vanished = confirm_vanished(session, skey, [k for k in known if k not in current and k[0] not in failed])
    renamed = match_renames(vanished, created, known, raw_cell)
    tombstones = STATE.setdefault("tombstones", {}).setdefault(skey, set())
    tombstones &= set(dbs)
    new_dbs = {d for d in dbs if d != DEFAULT_DB and d not in known_dbs and d not in tombstones}
    gone_dbs = {d for d in known_dbs if d not in dbs and d not in failed}
    plan = (list(created.items()), updated, renamed, vanished, new_dbs, gone_dbs)
    if any(plan):
        apply_changes(skey, *plan)


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
                for table in ("known", "known_dbs", "ignored", "tombstones"):
                    STATE.get(table, {}).pop(session_key(self), None)
        if session_alive(self):
            guarded("stop", before_stop)
        return original(self)
    stop._notisbook_original = original
    return stop


def patch(module):
    cls = getattr(module, "SparkSession", None)
    if cls is None:
        return
    builder = getattr(cls, "Builder", None)
    if builder is not None and "getOrCreate" in vars(builder):
        builder.getOrCreate = wrap_get_or_create(unwrap(vars(builder)["getOrCreate"]))
    if "stop" in vars(cls):
        cls.stop = wrap_stop(unwrap(vars(cls)["stop"]))


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
    session, _ = cell_session(True)
    if session is not None:
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


def build_ensure_code(db_path: str, managed_root: str, iceberg_warehouse: str) -> str:
    """Return the idempotent snippet that installs the catalog hook with the given paths."""
    config = json.dumps({"db_path": db_path, "managed_root": managed_root, "iceberg_warehouse": iceberg_warehouse})
    source = _KERNEL_TEMPLATE.replace("__CONFIG__", repr(config)).replace(
        "__MANAGED_HELPERS__", inspect.getsource(managed_table_dir).rstrip()
    )
    version = hashlib.sha1(source.encode()).hexdigest()[:12]
    ensure = (
        _ENSURE_TEMPLATE.replace("__MODULE__", repr(MODULE_NAME))
        .replace("__VERSION__", repr(version))
        .replace("__SOURCE__", repr(source))
    )
    return f"exec({ensure!r}, {{}})"
