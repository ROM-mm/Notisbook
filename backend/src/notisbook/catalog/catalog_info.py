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
KNOWN_CATALOGS = (registry.SPARK_CATALOG, iceberg_jdbc.ICEBERG_CATALOG, registry.HUDI_CATALOG)

_SENSITIVE = re.compile(r"(?i)secret|password|token|access[.]?key|credential")
# `user:pass@` (ou `user@`) logo após `://`, em qualquer URI, inclusive `jdbc:...://`.
_USERINFO = re.compile(r"(?<=://)[^/@\s]+@")
_WAREHOUSE_KEY = "spark.sql.warehouse.dir"
_CATALOG_KEY = "spark.sql.catalog."


def redact(key: str, value: str) -> tuple[str, bool]:
    """Valor a expor e se foi mascarado: chave ou valor sensível some inteiro; userinfo de URI vira `***@`."""
    if _SENSITIVE.search(key) or _SENSITIVE.search(value):
        return MASK, True
    masked = _USERINFO.sub("***@", value)
    return masked, masked != value


def _config_for(home: Path, catalog: str) -> list[tuple[str, str]]:
    """Linhas de `catalog_conf` do catálogo; o `hudi` herda as do `spark_catalog`. Vazio se `home` não serve de URL JDBC."""
    try:
        conf = bundles.catalog_conf(home)
    except bundles.UnsupportedHome:
        return []
    name = registry.SPARK_CATALOG if catalog == registry.HUDI_CATALOG else catalog
    prefix = f"{_CATALOG_KEY}{name}"
    keep = [(k, v) for k, v in conf if k == prefix or k.startswith(f"{prefix}.")]
    if name == registry.SPARK_CATALOG:
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
        spark_default = {"namespaces": [{"name": registry.DEFAULT_DATABASE, "tables": 0, "views": 0}], "tables": 0, "views": 0, "formats": {}}
        return STATUS_EMPTY, spark_default if catalog == registry.SPARK_CATALOG else empty
    return STATUS_OK, registry.catalog_summary(conn, hudi=catalog == registry.HUDI_CATALOG)


def build_catalog_info(home: Path, catalog: str, conn: sqlite3.Connection | None) -> dict[str, Any]:
    """Painel do catálogo (`KNOWN_CATALOGS`); `sqlite3.Error` do spark/hudi sobe ao chamador, o do Iceberg vira status."""
    status, summary = _summary_or_status(conn, catalog)
    conf = _config_for(home, catalog)
    values = dict(conf)
    prefix = f"{_CATALOG_KEY}{registry.SPARK_CATALOG if catalog == registry.HUDI_CATALOG else catalog}"
    is_iceberg = catalog == iceberg_jdbc.ICEBERG_CATALOG
    namespaces = summary["namespaces"]
    config = []
    for key, value in conf:
        shown, redacted = redact(key, value)
        config.append({"key": key, "value": shown, "redacted": redacted})
    return {
        "name": catalog,
        "kind": {registry.SPARK_CATALOG: "session", iceberg_jdbc.ICEBERG_CATALOG: "named"}.get(catalog, "display_group"),
        "backing_catalog": registry.SPARK_CATALOG if catalog == registry.HUDI_CATALOG else None,
        "status": status,
        "profile": PROFILE,
        "implementation": _safe(prefix, values.get(prefix)),
        "type": _safe(f"{prefix}.type", values.get(f"{prefix}.type")) if is_iceberg else "delta",
        "warehouse": _safe("warehouse", values.get(f"{prefix}.warehouse" if is_iceberg else _WAREHOUSE_KEY)),
        "uri": _safe("uri", values.get(f"{prefix}.uri")),
        "file_io": _safe("io-impl", values.get(f"{prefix}.io-impl")),
        "counts": {"namespaces": len(namespaces), "tables": summary["tables"], "views": summary["views"]},
        "formats": summary["formats"],
        "namespaces": namespaces[:MAX_NAMESPACES],
        "namespaces_truncated": len(namespaces) > MAX_NAMESPACES,
        "config": config,
    }
