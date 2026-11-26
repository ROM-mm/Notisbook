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
from ...notislake.locations import known_buckets
from ...notislake.sparkconf import SCOPE_ANY

REST_PATH = "/iceberg"
SECRET_S3 = "notisbook_s3"
SECRET_S3_DENY = "notisbook_s3_deny"
SECRET_ICEBERG = "notisbook_iceberg"
CATALOG = "notislake"
# Esquemas S3 que o DuckDB aceita; o mesmo bucket sob todos eles, pois um SCOPE só com um esquema dá 403 nos outros.
_S3_SCHEMES = ("s3", "s3a", "s3n")
# A barra final impede casar outro bucket com o mesmo prefixo (`s3://notislake-outro`).
S3_SCOPES = tuple(f"{scheme}://{bucket}/" for bucket in known_buckets() for scheme in _S3_SCHEMES)
# Fail-closed: qualquer outro bucket cai neste secret, de escopo mais curto, e vai para uma porta morta
# (a mesma do Spark) em vez de sair sem credencial para a AWS. O SCOPE mais longo do secret real vence nos buckets conhecidos.
DENY_SCOPES = tuple(f"{scheme}://" for scheme in _S3_SCHEMES)
DENY_ENDPOINT = "127.0.0.1:1"
REQUIRED_EXTENSIONS = ("httpfs", "iceberg", "avro")
# Manual: opções por bucket `notislake`; automático: opções globais. Valendo a regra do Hadoop, a do bucket vence.
_S3A_PREFIXES = ("fs.s3a.bucket.notislake.", "fs.s3a.")

_TEMPLATE = r'''
import json, re, sys
cfg = json.loads(__PAYLOAD__)
state = sys.modules[__MODULE__].STATE
secrets = [v for v in (cfg.get("key_id"), cfg.get("secret"), cfg.get("token")) if v]

def q(value):
    return "'" + str(value).replace("'", "''") + "'"

def redact(text):
    # O erro do DuckDB pode ecoar o SQL, onde o segredo aparece escapado (`'` -> `''`).
    for s in secrets:
        for form in (s, s.replace("'", "''")):
            text = text.replace(form, "***")
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
    if cfg["deny_scopes"]:
        con.execute(
            "CREATE OR REPLACE TEMPORARY SECRET " + cfg["deny_name"] + " (TYPE S3, KEY_ID 'denied', SECRET 'denied', ENDPOINT "
            + q(cfg["deny_endpoint"]) + ", URL_STYLE 'path', USE_SSL false, REGION 'us-east-1', SCOPE ["
            + ", ".join(q(s) for s in cfg["deny_scopes"]) + "])"
        )
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


def _option(options: Mapping[str, str] | None, name: str) -> str | None:
    """Valor da opção S3A `name`, por bucket `notislake` ou global; a do bucket vence."""
    for prefix in _S3A_PREFIXES:
        value = (options or {}).get(prefix + name)
        if value is not None:
            return value
    return None


def _s3_settings(options: Mapping[str, str] | None) -> dict[str, object] | None:
    """Deriva endpoint host:porta, TLS e região das opções S3A da sessão; sem opções, sem secret S3."""
    endpoint = _option(options, "endpoint")
    if endpoint is None:
        return None
    parts = urlsplit(endpoint)
    return {
        "endpoint": parts.netloc,
        "ssl": parts.scheme == "https",
        "region": _option(options, "endpoint.region") or "us-east-1",
    }


def build_bootstrap_code(
    ext_dir: str,
    extensions: tuple[str, ...],
    options: Mapping[str, str] | None,
    port: int,
    token: str,
    s3a_scope: str = "notislake",
) -> str:
    """Snippet que prepara a conexão DuckDB do kernel; `options` são as opções S3A (com segredo) da sessão.

    `any` (automático): o secret real cobre `s3://`, `s3a://` e `s3n://` e não há secret deny, pois todo bucket só
    alcança o MinIO local; o escopo mais longo vence, então bucket novo funciona sem reiniciar. Outro valor
    (manual): secret só nos buckets conhecidos e deny nos demais esquemas.
    """
    s3 = _s3_settings(options)
    any_bucket = s3a_scope == SCOPE_ANY and s3 is not None
    payload: dict[str, object] = {
        "ext_dir": ext_dir,
        "extensions": list(extensions),
        "required": list(REQUIRED_EXTENSIONS),
        "s3": s3,
        "s3_name": SECRET_S3,
        "ice_name": SECRET_ICEBERG,
        "scopes": list(DENY_SCOPES if any_bucket else S3_SCOPES),
        "deny_name": SECRET_S3_DENY,
        "deny_scopes": [] if any_bucket else list(DENY_SCOPES),
        "deny_endpoint": DENY_ENDPOINT,
        "key_id": _option(options, "access.key"),
        "secret": _option(options, "secret.key"),
        "token": token,
        "catalog": CATALOG,
        "rest": f"http://127.0.0.1:{port}{REST_PATH}",
    }
    source = _TEMPLATE.replace("__MODULE__", repr(MODULE_NAME)).replace("__PAYLOAD__", repr(json.dumps(payload)))
    return f"exec({source!r}, {{}})"
