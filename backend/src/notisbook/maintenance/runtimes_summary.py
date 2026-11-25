"""`notisbook --runtimes-summary`: lista os runtimes Spark e DuckDB gerenciados e termina, sem subir servidor.

Chamado pelo `install.sh` para o resumo final. Somente leitura: não toma o flock nem cria nada na pasta de dados.
Docker e Glue ficam de fora: não têm env próprio em `<home>/envs`. Exit: 0 sempre que a leitura termina.
Mensagens em inglês.
"""

from ..config import default_home
from ..runtimes.duckdb import kernelspec as duckdb_kernelspec
from ..spark import kernelspec as spark_kernelspec

EMPTY_MESSAGE = "  (none — add them in Settings › Runtimes)"


def run() -> int:
    """Imprime uma linha por runtime gerenciado (nome e pasta do env); devolve 0."""
    home = default_home()
    rows = [(e.display_name, e.env_dir) for e in spark_kernelspec.discover(home)]
    rows += [(e.display_name, e.env_dir) for e in duckdb_kernelspec.discover(home)]
    if not rows:
        print(EMPTY_MESSAGE)
        return 0
    width = max(len(name) for name, _ in rows)
    for name, env_dir in rows:
        print(f"  {name:<{width}}   {env_dir}")
    return 0
