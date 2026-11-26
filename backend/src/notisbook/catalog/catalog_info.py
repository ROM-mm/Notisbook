"""Resposta do painel "Catalog info": contagens exatas do `catalog.db` e a config do perfil Spark local.

Sem kernel: a config vem de `bundles.catalog_conf`, a mesma fonte do `spark-defaults.conf`. Valores
sensíveis são mascarados aqui; o valor real nunca sai do backend.
"""

import re
import sqlite3
from pathlib import Path
from typing import Any

from ..spark import bundles
from . import iceberg_jdbc, registry

PROFILE = "local"
MAX_NAMESPACES = 1000
MASK = "********"
STATUS_OK = "ok"
STATUS_EMPTY = "empty"
KNOWN_CATALOGS = (registry.SPARK_CATALOG, iceberg_jdbc.ICEBERG_CATALOG)

_SENSITIVE = re.compile(r"(?i)secret|password|token|access[.]?key|credential")
# `user:pass@` (ou `user@`) logo após `://`, em qualquer URI, inclusive `jdbc:...://`.
_USERINFO = re.compile(r"(?<=://)[^/@\s]+@")
_WAREHOUSE_KEY = "spark.sql.warehouse.dir"


def redact(key: str, value: str) -> tuple[str, bool]:
    """Valor a expor e se foi mascarado: chave sensível some inteira; userinfo de URI vira `***@`.

    Só a chave decide: o valor pode conter o home do usuário (ex. um caminho com "token") sem ser segredo.
    """
    if _SENSITIVE.search(key):
        return MASK, True
    masked = _USERINFO.sub("***@", value)
    return masked, masked != value


def _config_for(home: Path, catalog: str) -> list[tuple[str, str]]:
    """Linhas de `catalog_conf` do catálogo. Vazio se `home` não serve de URL JDBC."""
    try:
        conf = bundles.catalog_conf(home)
    except bundles.UnsupportedHome:
        return []
    prefix = f"{bundles.CATALOG_PREFIX}{catalog}"
    keep = [(k, v) for k, v in conf if k == prefix or k.startswith(f"{prefix}.")]
    if catalog == registry.SPARK_CATALOG:
        keep += [(k, v) for k, v in conf if k == _WAREHOUSE_KEY]
    return keep


def _safe(key: str, value: str | None) -> str | None:
    return None if value is None else redact(key, value)[0]


def _summary_or_status(conn: sqlite3.Connection | None, catalog: str) -> tuple[str, dict[str, Any]]:
    """`(status, summary)`; o Iceberg com schema ou leitura inválidos degrada (mesmos códigos de `error_entry`)."""
    empty: dict[str, Any] = {"namespaces": [], "tables": 0, "views": 0, "formats": {}}
    if catalog == iceberg_jdbc.ICEBERG_CATALOG:
        if conn is None:
            return STATUS_EMPTY, empty
        try:
            return STATUS_OK, iceberg_jdbc.catalog_summary(conn)
        except iceberg_jdbc.UnsupportedIcebergSchema:
            return iceberg_jdbc.ERR_UNSUPPORTED, empty
        except sqlite3.Error:
            return iceberg_jdbc.ERR_UNREADABLE, empty
    if conn is None:
        layers = [{"name": ns, "tables": 0, "views": 0} for ns in registry.empty_display_names()]
        return STATUS_EMPTY, {**empty, "namespaces": layers}
    return STATUS_OK, registry.catalog_summary(conn)


def build_catalog_info(home: Path, catalog: str, conn: sqlite3.Connection | None) -> dict[str, Any]:
    """Painel do catálogo (`KNOWN_CATALOGS`); `sqlite3.Error` do spark sobe ao chamador, o do Iceberg vira status."""
    status, summary = _summary_or_status(conn, catalog)
    conf = _config_for(home, catalog)
    values = dict(conf)
    prefix = f"{bundles.CATALOG_PREFIX}{catalog}"
    is_iceberg = catalog == iceberg_jdbc.ICEBERG_CATALOG
    namespaces = summary["namespaces"]
    config = []
    for key, value in conf:
        shown, redacted = redact(key, value)
        config.append({"key": key, "value": shown, "redacted": redacted})
    return {
        "name": catalog,
        "kind": "session" if catalog == registry.SPARK_CATALOG else "named",
        "backing_catalog": None,
        "status": status,
        "profile": PROFILE,
        "implementation": _safe(prefix, values.get(prefix)),
        "type": _safe(f"{prefix}.type", values.get(f"{prefix}.type")) if is_iceberg else ("delta" if conf else None),
        "warehouse": _safe("warehouse", values.get(f"{prefix}.warehouse" if is_iceberg else _WAREHOUSE_KEY)),
        "uri": _safe("uri", values.get(f"{prefix}.uri")),
        "file_io": _safe("io-impl", values.get(f"{prefix}.io-impl")),
        "counts": {"namespaces": len(namespaces), "tables": summary["tables"], "views": summary["views"]},
        "formats": summary["formats"],
        "namespaces": namespaces[:MAX_NAMESPACES],
        "namespaces_truncated": len(namespaces) > MAX_NAMESPACES,
        "config": config,
    }
