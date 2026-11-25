"""Versões dos runtimes instalados na primeira instalação (`notisbook --install-default-runtimes`).

Fonte única: o `install.sh` não conhece versão; trocar o padrão muda só a wheel. Cada versão precisa
existir no catálogo do Spark (`spark/bundles.py`) e no manifesto do DuckDB (`runtimes/duckdb/extensions.json`).
"""

DEFAULT_SPARK_VERSION = "4.1.4"
DEFAULT_DUCKDB_VERSION = "2.0.1"
