"""`notisbook --runtimes-summary`: lista os runtimes Spark e DuckDB gerenciados e termina, sem subir servidor.

Chamado pelo `install.sh` para o resumo final. Somente leitura: não toma o flock nem cria nada na pasta de dados.
Docker e Glue ficam de fora: não têm env próprio em `<home>/envs`. Sem Spark gerenciado e sem JDK compatível,
acrescenta uma linha explicando por que o Spark padrão não entrou. Exit: 0 sempre que a leitura termina.
Mensagens em inglês.
"""

import asyncio

from ..config import default_home
from ..runtimes.defaults import DEFAULT_SPARK_VERSION
from ..runtimes.duckdb import kernelspec as duckdb_kernelspec
from ..spark import kernelspec as spark_kernelspec
from ..spark.prereqs import jdk_candidates, jdk_for_spark

EMPTY_MESSAGE = "  (none — add them in Settings › Runtimes)"


def run() -> int:
    """Imprime uma linha por runtime gerenciado (nome e pasta do env); devolve 0."""
    home = default_home()
    spark = [(e.display_name, e.env_dir) for e in spark_kernelspec.discover(home)]
    rows = spark + [(e.display_name, e.env_dir) for e in duckdb_kernelspec.discover(home)]
    if rows:
        width = max(len(name) for name, _ in rows)
        for name, env_dir in rows:
            print(f"  {name:<{width}}   {env_dir}")
    else:
        print(EMPTY_MESSAGE)
    if not spark and asyncio.run(jdk_for_spark(DEFAULT_SPARK_VERSION)) is None:
        majors = " or ".join(str(m) for m in jdk_candidates(DEFAULT_SPARK_VERSION))
        print(f"  Apache Spark: not installed — no JDK {majors} found; install one, then add Spark in Settings › Runtimes")
    return 0
