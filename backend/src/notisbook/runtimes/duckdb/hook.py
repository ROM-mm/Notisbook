"""Bootstrap do kernel DuckDB: conexão própria com extensões offline, secret S3 e catálogo `notislake`.

O snippet vai por `execute` silencioso (canal ZMQ autenticado pelo connection file 0600), o mesmo
caminho do hook Spark: credenciais e token não passam por argv, kernel.json, os.environ nem log.
O snippet nunca levanta (a falha vira `STATE["duckdb_error"]`, já redigida), para o traceback
da célula, que reproduziria o código, não carregar segredo.
"""

import json
from collections.abc import Mapping
from urllib.parse import urlsplit

from ...kernels.sql_cell import MODULE_NAME

REST_PATH = "/iceberg"
SECRET_S3 = "notisbook_s3"
SECRET_ICEBERG = "notisbook_iceberg"
CATALOG = "notislake"
# Mesmo bucket com os dois esquemas: um SCOPE só com um deles dá 403 no outro.
S3_SCOPES = ("s3://notislake", "s3a://notislake")
REQUIRED_EXTENSIONS = ("httpfs", "iceberg", "avro")
_S3A_PREFIX = "fs.s3a.bucket.notislake."

_TEMPLATE = r'''
import json, re, sys
cfg = json.loads(__PAYLOAD__)
state = sys.modules[__MODULE__].STATE
secrets = [v for v in (cfg.get("key_id"), cfg.get("secret"), cfg.get("token")) if v]

def q(value):
    return "'" + str(value).replace("'", "''") + "'"

def redact(text):
    for s in secrets:
        text = text.replace(s, "***")
    return text

con = None
try:
    import duckdb
    old = state.pop("duckdb", None)
    state.pop("duckdb_error", None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    if not cfg["ext_dir"]:
        raise RuntimeError("extension directory missing in the kernelspec; reinstall the DuckDB runtime")
    con = duckdb.connect(":memory:", config={
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "extension_directory": cfg["ext_dir"],
    })
    for name in cfg["extensions"]:
        if not re.fullmatch(r"[a-z0-9_]+", name):
            continue
        try:
            con.execute("LOAD " + name)
        except Exception:
            if name in cfg["required"]:
                raise
    if cfg.get("s3"):
        s3 = cfg["s3"]
        con.execute(
            "CREATE OR REPLACE TEMPORARY SECRET " + cfg["s3_name"] + " (TYPE S3, KEY_ID " + q(cfg["key_id"])
            + ", SECRET " + q(cfg["secret"]) + ", ENDPOINT " + q(s3["endpoint"]) + ", URL_STYLE 'path', USE_SSL "
            + ("true" if s3["ssl"] else "false") + ", REGION " + q(s3["region"])
            + ", SCOPE [" + ", ".join(q(s) for s in cfg["scopes"]) + "])"
        )
    con.execute(
        "CREATE OR REPLACE TEMPORARY SECRET " + cfg["ice_name"] + " (TYPE iceberg, TOKEN " + q(cfg["token"]) + ")"
    )
    con.execute(
        "ATTACH " + q(cfg["catalog"]) + " AS " + cfg["catalog"] + " (TYPE iceberg, ENDPOINT " + q(cfg["rest"])
        + ", SECRET " + cfg["ice_name"] + ")"
    )
    state["duckdb"] = con
except BaseException as exc:
    state["duckdb_error"] = type(exc).__name__ + ": " + redact(str(exc))[:300]
    if con is not None:
        try:
            con.close()
        except Exception:
            pass
'''


def _s3_settings(options: Mapping[str, str] | None) -> dict[str, object] | None:
    """Deriva endpoint host:porta, TLS e região das opções S3A da sessão; sem opções, sem secret S3."""
    if not options:
        return None
    parts = urlsplit(options[f"{_S3A_PREFIX}endpoint"])
    return {
        "endpoint": parts.netloc,
        "ssl": parts.scheme == "https",
        "region": options.get(f"{_S3A_PREFIX}endpoint.region", "us-east-1"),
    }


def build_bootstrap_code(
    ext_dir: str,
    extensions: tuple[str, ...],
    options: Mapping[str, str] | None,
    port: int,
    token: str,
) -> str:
    """Snippet que prepara a conexão DuckDB do kernel; `options` são as opções S3A (com segredo) da sessão."""
    payload: dict[str, object] = {
        "ext_dir": ext_dir,
        "extensions": list(extensions),
        "required": list(REQUIRED_EXTENSIONS),
        "s3": _s3_settings(options),
        "s3_name": SECRET_S3,
        "ice_name": SECRET_ICEBERG,
        "scopes": list(S3_SCOPES),
        "key_id": (options or {}).get(f"{_S3A_PREFIX}access.key"),
        "secret": (options or {}).get(f"{_S3A_PREFIX}secret.key"),
        "token": token,
        "catalog": CATALOG,
        "rest": f"http://127.0.0.1:{port}{REST_PATH}",
    }
    source = _TEMPLATE.replace("__MODULE__", repr(MODULE_NAME)).replace("__PAYLOAD__", repr(json.dumps(payload)))
    return f"exec({source!r}, {{}})"
