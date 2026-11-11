"""Sondas silenciosas das variáveis do kernel, avaliadas dentro do kernel do usuário.

O pedido é um `execute` com `silent=True` e uma única `user_expressions`. A expressão monta
os helpers num dict descartável, sem tocar no namespace do usuário, e não importa pyspark.
"""

import ast
import json
from dataclasses import dataclass
from typing import Any, Literal

VarOp = Literal["variables", "children"]
EXPRESSION_KEY = "nb"

# Variáveis do kernel: despacho por tipo, sem repr()/len() genéricos nem atributos de objetos
# desconhecidos (um DataFrame passado ao formatador do IPython dispararia job Spark). Não
# depende de SparkSession. Caminho = [nome, passo, ...]; passo str = atributo/campo, int = posição.
MAX_CHILDREN = 100
MAX_PATH_DEPTH = 16

_VARIABLES_SOURCE = '''
import itertools, json, reprlib, sys, time, types
from IPython import get_ipython

SUMMARY = 200
NAME_MAX = 200
MAX_VARS = 500
MAX_PAGE = 100
MAX_SCAN = 10000
MAX_DEPTH = 16
PREVIEW = 8
BUDGET = 2.0
SPECIAL = frozenset(("In", "Out", "exit", "quit", "get_ipython"))
SCALARS = (int, float, bool, complex, str, bytes, bytearray, type(None))
MISSING = object()
SPARK = {
    "pyspark.sql.session.SparkSession": "spark_session",
    "pyspark.sql.connect.session.SparkSession": "spark_session",
    "pyspark.sql.dataframe.DataFrame": "spark_df",
    "pyspark.sql.connect.dataframe.DataFrame": "spark_df",
    "pyspark.sql.types.StructType": "spark_struct",
    "pyspark.sql.types.StructField": "spark_field",
    "pyspark.sql.types.Row": "spark_row",
    "pyspark.sql.column.Column": "spark_column",
    "pyspark.sql.connect.column.Column": "spark_column",
    "pyspark.rdd.RDD": "spark_rdd",
}
PANDAS = {
    "pandas.core.frame.DataFrame": "pandas.DataFrame",
    "pandas.core.series.Series": "pandas.Series",
    "pandas.core.indexes.base.Index": "pandas.Index",
}

_R = reprlib.Repr()
_R.maxstring = SUMMARY
_R.maxother = SUMMARY
_R.maxlong = 40

class _Lookup(Exception):
    pass

def _cut(text, size=SUMMARY):
    text = str(text)
    return text if len(text) <= size else text[: size - 3] + "..."

def _cname(cls):
    try:
        return str(type.__getattribute__(cls, "__module__")) + "." + str(type.__getattribute__(cls, "__qualname__"))
    except Exception:
        return "?"

def _tname(obj):
    try:
        return str(type.__getattribute__(type(obj), "__name__"))
    except Exception:
        return "object"

def _mro(obj):
    try:
        # Lê o slot de `type` direto: `type(obj).__mro__` passaria pela metaclasse (código do usuário).
        return type.__dict__["__mro__"].__get__(type(obj))
    except Exception:
        return (type(obj),)

def _has(mro, *classes):
    return any(c is k for c in mro for k in classes)

def _native_get(obj, name, kinds):
    # Só descritores nativos (slot/getset do CPython) são lidos; property e
    # descritores de usuário podem executar código arbitrário e são ignorados.
    for c in _mro(obj):
        try:
            desc = type.__getattribute__(c, "__dict__")[name]
        except Exception:
            continue
        if type(desc) not in kinds:
            raise AttributeError(name)
        return desc.__get__(obj, type(obj))
    raise AttributeError(name)

def _odict(obj):
    try:
        found = _native_get(obj, "__dict__", (types.GetSetDescriptorType, types.MemberDescriptorType))
    except Exception:
        return {}
    return found if type(found) is dict else {}

def _kind(obj):
    t = type(obj)
    if t in SCALARS:
        return "scalar"
    if t is list or t is tuple:
        return "seq"
    if t is set or t is frozenset:
        return "set"
    if t is dict:
        return "map"
    mro = _mro(obj)
    if _has(mro, types.ModuleType):
        return "module"
    if _has(mro, type):
        return "class"
    if _has(mro, types.FunctionType, types.BuiltinFunctionType, types.MethodType):
        return "function"
    names = [_cname(c) for c in mro]
    if "pyspark" in sys.modules:
        for n in names:
            if n in SPARK:
                return SPARK[n]
    if "numpy" in sys.modules and ("numpy.ndarray" in names or "numpy.generic" in names):
        return "numpy"
    if "pandas" in sys.modules and any(n in PANDAS for n in names):
        return "pandas"
    return "object"

def _brief(x):
    t = type(x)
    if t in SCALARS and t is not bytes and t is not bytearray:
        return _cut(_R.repr(x), 40)
    return "<" + _tname(x) + ">"

def _join(opener, parts, more, closer):
    body = ", ".join(parts)
    if more:
        body += ", ..." if parts else "..."
    return _cut(opener + body + closer)

def _ftype(field):
    return _cut(field.dataType.simpleString(), 80)

def _fields_text(fields):
    parts = [str(f.name) + ": " + _ftype(f) for f in fields[:PREVIEW]]
    return _join("", parts, len(fields) > PREVIEW, "")

def _cols(n):
    return str(n) + (" col" if n == 1 else " cols")

def _session_info(s):
    try:
        sc = s.sparkContext
    except Exception:
        sc = None
    if sc is None:
        rows = [("mode", lambda: "connect"), ("version", lambda: s.version)]
    else:
        rows = [
            ("appName", lambda: sc.appName), ("master", lambda: sc.master), ("version", lambda: s.version),
            ("uiWebUrl", lambda: sc.uiWebUrl), ("applicationId", lambda: sc.applicationId),
        ]
    out = []
    for key, fn in rows:
        try:
            value = fn()
        except Exception:
            continue
        if value is not None:
            out.append((key, _cut(value)))
    return out

def _struct_fields(obj, kind):
    if kind == "spark_df":
        return list(obj.schema.fields)
    if kind == "spark_struct":
        return list(obj.fields)
    if kind == "spark_field":
        dt = obj.dataType
        return list(dt.fields) if _kind(dt) == "spark_struct" else []
    return []

def _row_names(obj, n):
    try:
        names = obj.__fields__
    except Exception:
        return None
    return list(names) if type(names) in (list, tuple) and len(names) == n else None

def _obj_items(obj):
    out, seen = [], set(("__dict__", "__weakref__"))
    for c in _mro(obj):
        try:
            slots = type.__getattribute__(c, "__dict__").get("__slots__", ())
        except Exception:
            continue
        if type(slots) is str:
            slots = (slots,)
        if type(slots) not in (tuple, list):
            continue
        for s in slots:
            if type(s) is not str or s in seen:
                continue
            seen.add(s)
            try:
                out.append((s, _native_get(obj, s, (types.MemberDescriptorType,))))
            except Exception:
                continue
    for k, v in itertools.islice(_odict(obj).items(), MAX_SCAN):
        if type(k) is str and k not in seen:
            out.append((k, v))
    return out

def _d_scalar(obj):
    if type(obj) is bytes or type(obj) is bytearray:
        text = repr(bytes(obj[:SUMMARY])) + ("..." if len(obj) > SUMMARY else "")
    else:
        text = _R.repr(obj)
    return type(obj).__name__, _cut(text), False

def _d_seq(obj):
    n = len(obj)
    parts = [_brief(x) for x in itertools.islice(obj, PREVIEW)]
    opener, closer = ("[", "]") if type(obj) is list else ("(", ")")
    return type(obj).__name__ + ": " + str(n), _join(opener, parts, n > PREVIEW, closer), n > 0

def _d_set(obj):
    n = len(obj)
    parts = [_brief(x) for x in itertools.islice(obj, PREVIEW)]
    return type(obj).__name__ + ": " + str(n), _join("{", parts, n > PREVIEW, "}") if n else "set()", n > 0

def _d_map(obj):
    n = len(obj)
    parts = [_brief(k) + ": " + _brief(v) for k, v in itertools.islice(obj.items(), PREVIEW)]
    return "dict: " + str(n), _join("{", parts, n > PREVIEW, "}") if n else "{}", n > 0

def _d_session(obj):
    info = dict(_session_info(obj))
    head = [info[k] for k in ("appName", "mode") if k in info]
    if "version" in info:
        head.append("v" + info["version"])
    return "SparkSession", _cut(" - ".join(head) or "SparkSession"), True

def _d_df(obj):
    try:
        fields = _struct_fields(obj, "spark_df")
    except Exception:
        return "DataFrame", "<schema unavailable>", False
    flags = []
    try:
        if obj.is_cached:
            flags.append("cached")
    except Exception:
        pass
    if _cname(type(obj)).startswith("pyspark.sql.") and ".connect." not in _cname(type(obj)):
        try:
            if obj.isStreaming:
                flags.append("streaming")
        except Exception:
            pass
    prefix = "[" + ", ".join(flags) + "] " if flags else ""
    return "DataFrame: " + _cols(len(fields)), _cut(prefix + _fields_text(fields)), len(fields) > 0

def _d_struct(obj):
    fields = _struct_fields(obj, "spark_struct")
    return "StructType: " + str(len(fields)), _cut(_fields_text(fields)), len(fields) > 0

def _d_field(obj):
    fields = _struct_fields(obj, "spark_field")
    return "StructField", _cut(str(obj.name) + ": " + _ftype(obj)), len(fields) > 0

def _d_row(obj):
    n = tuple.__len__(obj)
    values = tuple.__getitem__(obj, slice(0, PREVIEW))
    names = _row_names(obj, n)
    parts = [(str(names[i]) + "=" if names else "") + _brief(v) for i, v in enumerate(values)]
    return "Row: " + str(n), _join("Row(", parts, n > PREVIEW, ")"), n > 0

def _d_rdd(obj):
    try:
        rid = obj._id
    except Exception:
        rid = None
    return "RDD", "RDD" + (" id=" + str(rid) if rid is not None else ""), False

def _d_column(obj):
    return "Column", "Column", False

def _d_numpy(obj):
    dtype = str(obj.dtype)
    shape = tuple(int(i) for i in obj.shape)
    if "numpy.ndarray" in [_cname(c) for c in _mro(obj)]:
        return "ndarray: " + str(shape), "dtype=" + dtype + ", shape=" + str(shape), False
    return _tname(obj), "dtype=" + dtype, False

def _d_pandas(obj):
    label = "pandas.Index"
    for c in _mro(obj):
        if _cname(c) in PANDAS:
            label = PANDAS[_cname(c)]
            break
    shape = tuple(int(i) for i in obj.shape)
    if label == "pandas.DataFrame":
        return label + ": " + _cols(shape[1]), "shape=" + str(shape), False
    return label + ": " + str(shape[0]), "dtype=" + str(obj.dtype) + ", len=" + str(shape[0]), False

def _d_module(obj):
    return "module", _cut("<module " + repr(str(_odict(obj).get("__name__", "?"))) + ">"), False

def _d_class(obj):
    name = _cname(obj)
    return _tname(obj), _cut("<class " + repr(name) + ">"), False

def _d_function(obj):
    try:
        name = str(_native_get(obj, "__name__", (types.GetSetDescriptorType, types.MemberDescriptorType)))
    except Exception:
        name = "?"
    return _tname(obj), _cut("<function " + name + ">"), False

def _d_object(obj):
    text = "<" + _cname(type(obj)) + " object at " + hex(id(obj)) + ">"
    return _tname(obj), _cut(text), len(_obj_items(obj)) > 0

DESCRIBE = {
    "scalar": _d_scalar, "seq": _d_seq, "set": _d_set, "map": _d_map,
    "spark_session": _d_session, "spark_df": _d_df, "spark_struct": _d_struct, "spark_field": _d_field,
    "spark_row": _d_row, "spark_rdd": _d_rdd, "spark_column": _d_column,
    "numpy": _d_numpy, "pandas": _d_pandas,
    "module": _d_module, "class": _d_class, "function": _d_function, "object": _d_object,
}

def _describe(obj, kind=None):
    return DESCRIBE[kind or _kind(obj)](obj)

def _entry(key, name, value):
    try:
        typ, summary, expandable = _describe(value)
    except Exception:
        typ, summary, expandable = _tname(value), "<unavailable>", False
    return {"key": key, "name": _cut(name, NAME_MAX), "type": typ, "summary": summary, "expandable": expandable}

def _field_entry(i, f):
    try:
        expandable = len(_struct_fields(f, "spark_field")) > 0
        return {"key": i, "name": _cut(f.name, NAME_MAX), "type": _ftype(f),
                "summary": "nullable" if f.nullable else "not null", "expandable": expandable}
    except Exception:
        return _entry(i, "?", f)

def _kids(obj, offset, limit, deadline):
    kind = _kind(obj)
    stop = offset + limit
    if kind == "seq":
        total, items = len(obj), [(i, str(i), obj[i]) for i in range(offset, min(len(obj), stop))]
    elif kind == "set":
        total, items = len(obj), [(offset + i, str(offset + i), v) for i, v in enumerate(itertools.islice(obj, offset, stop))]
    elif kind == "map":
        total = len(obj)
        items = [(offset + i, _brief(k), v) for i, (k, v) in enumerate(itertools.islice(obj.items(), offset, stop))]
    elif kind == "spark_row":
        n = tuple.__len__(obj)
        names = _row_names(obj, n)
        values = tuple.__getitem__(obj, slice(offset, stop))
        total = n
        items = [(offset + i, names[offset + i] if names else str(offset + i), v) for i, v in enumerate(values)]
    elif kind == "object":
        found = _obj_items(obj)
        total, items = len(found), [(k, k, v) for k, v in found[offset:stop]]
    elif kind == "spark_session":
        found = _session_info(obj)
        return len(found), [
            {"key": k, "name": k, "type": "str", "summary": v, "expandable": False} for k, v in found[offset:stop]
        ]
    elif kind in ("spark_df", "spark_struct", "spark_field"):
        fields = _struct_fields(obj, kind)
        return len(fields), [_field_entry(offset + i, f) for i, f in enumerate(fields[offset:stop])]
    else:
        return 0, []
    out = []
    for key, name, value in items:
        if time.monotonic() > deadline:
            break
        out.append(_entry(key, name, value))
    return total, out

def _step(obj, k):
    kind = _kind(obj)
    try:
        if kind == "object" or kind == "spark_session":
            if type(k) is not str:
                raise _Lookup()
            pairs = _obj_items(obj) if kind == "object" else _session_info(obj)
            for name, value in pairs:
                if name == k:
                    return value
            raise _Lookup()
        if type(k) is not int or k < 0:
            raise _Lookup()
        if kind == "seq":
            return obj[k]
        if kind == "set":
            return next(itertools.islice(obj, k, k + 1))
        if kind == "map":
            return next(itertools.islice(obj.items(), k, k + 1))[1]
        if kind in ("spark_df", "spark_struct", "spark_field"):
            return _struct_fields(obj, kind)[k]
        if kind == "spark_row":
            return tuple.__getitem__(obj, k)
    except (IndexError, StopIteration):
        raise _Lookup()
    raise _Lookup()

def _is_hidden(hidden, name, value):
    if type(hidden) is dict:
        return hidden.get(name, MISSING) is value
    return name in hidden

def _variables(ip, deadline):
    ns, hidden = ip.user_ns, ip.user_ns_hidden
    rows = []
    for name in list(ns):
        value = ns[name]
        if type(name) is not str or _is_hidden(hidden, name, value):
            continue
        kind = _kind(value)
        special = name.startswith("_") or name in SPECIAL or kind in ("module", "class", "function")
        rows.append((name, "special" if special else "user", kind, value))
    rows.sort(key=lambda r: (r[1] != "user", r[0].lower()))
    out, truncated = [], len(rows) > MAX_VARS
    for name, group, kind, value in rows[:MAX_VARS]:
        if time.monotonic() > deadline:
            truncated = True
            break
        try:
            typ, summary, expandable = _describe(value, kind)
        except Exception:
            typ, summary, expandable = _tname(value), "<unavailable>", False
        out.append({"name": _cut(name, NAME_MAX), "type": typ, "summary": summary,
                    "expandable": expandable, "group": group})
    count = max(int(ip.execution_count) - 1, 0)
    return {"executionCount": count, "total": len(rows), "truncated": truncated, "variables": out}

def _children(ip, args, deadline):
    path = args["path"]
    if type(path) is not list or not 0 < len(path) <= MAX_DEPTH or type(path[0]) is not str:
        raise _Lookup()
    if path[0] not in ip.user_ns:
        raise _Lookup()
    obj = ip.user_ns[path[0]]
    for k in path[1:]:
        obj = _step(obj, k)
    offset = max(int(args.get("offset", 0)), 0)
    limit = min(max(int(args.get("limit", MAX_PAGE)), 1), MAX_PAGE)
    total, children = _kids(obj, offset, limit, deadline)
    return {"children": children, "total": total, "offset": offset}

def run(op, raw_args):
    try:
        args = json.loads(raw_args)
        ip = get_ipython()
        if ip is None:
            return json.dumps({"status": "error", "message": "no_ipython"})
        deadline = time.monotonic() + BUDGET
        if op == "variables":
            data = _variables(ip, deadline)
        else:
            data = _children(ip, args, deadline)
    except _Lookup:
        return json.dumps({"status": "stale_path"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": type(exc).__name__ + ": " + str(exc)[:300]})
    return json.dumps({"status": "ok", "data": data})
'''


@dataclass(frozen=True)
class Probe:
    status: Literal["ok", "no_spark_session", "stale_path", "error"]
    data: Any = None
    message: str | None = None


def build_variables_request(op: VarOp, args: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Return `(code, user_expressions)` for a silent variables/children probe.

    `args` (path, offset, limit) travels as a JSON literal decoded in the kernel.
    """
    expression = f"(lambda g: (exec({_VARIABLES_SOURCE!r}, g), g['run']({op!r}, {json.dumps(args)!r}))[1])({{}})"
    return "", {EXPRESSION_KEY: expression}


def parse_reply(content: dict[str, Any]) -> Probe:
    """Decode an `execute_reply` content produced by `build_variables_request`."""
    if content.get("status") != "ok":
        return Probe("error", message=f"kernel replied {content.get('status', 'error')}")
    entry = (content.get("user_expressions") or {}).get(EXPRESSION_KEY) or {}
    if entry.get("status") != "ok":
        return Probe("error", message=str(entry.get("ename") or "expression_failed"))
    try:
        text = entry["data"]["text/plain"]
        payload = json.loads(ast.literal_eval(text))
    except (KeyError, ValueError, SyntaxError):
        return Probe("error", message="unreadable introspection reply")
    status = payload.get("status")
    if status == "ok":
        return Probe("ok", data=payload.get("data"))
    if status == "no_spark_session":
        return Probe("no_spark_session")
    if status == "stale_path":
        return Probe("stale_path")
    return Probe("error", message=payload.get("message", "introspection failed"))
