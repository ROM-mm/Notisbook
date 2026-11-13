# ADR-0002: Extensões no kernel por módulos ocultos instalados via execução silenciosa

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Recursos do Notisbook que precisam rodar dentro do processo do kernel — renderização de DataFrames, células Spark SQL e DuckDB SQL e sincronização da `SparkSession` com o catálogo persistente — não podem depender de pacotes extras instalados no ambiente do usuário nem poluir o namespace do notebook.

## Decisão
Ao iniciar uma sessão, o backend envia ao kernel uma execução silenciosa (`silent=True`, `store_history=False`) com código "ensure" idempotente que instala dois módulos ocultos em `sys.modules`:
- `_notisbook_display` (`kernels/sql_cell.py`): renderer de resultados (HTML + `text/plain`, com limites de linhas `MAX_ROWS`/`DISPLAY_ROWS`), execução de células SQL do Spark e DuckDB. A consulta SQL viaja como literal JSON decodificado no kernel, sem ser concatenada ao código.
- `_notisbook_catalog` (`kernels/catalog_hook.py`): intercepta `SparkSession.Builder.getOrCreate` e `SparkSession.stop` por um finder em `sys.meta_path`, hidrata a sessão a partir do registro `nb_*` e reconcilia criações, alterações e remoções após cada célula.

A configuração chega ao kernel como literais JSON (o kernel não lê variáveis de ambiente). O instalador confirma a presença do módulo por `user_expressions` (`ENSURE_CHECK`) e falhas apenas geram log, sem bloquear o kernel.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Nenhum pacote do Notisbook precisa existir no ambiente do kernel; o código é enviado a cada sessão.
- Namespace do usuário preservado; erros do hook não chegam à célula (ficam em `STATE["errors"]` e geram um aviso breve).
- Células SQL não sofrem injeção de código, pois a consulta é tratada como dado.

### Negativas
- Lógica relevante vive em strings de template (`_KERNEL_TEMPLATE`), o que dificulta análise estática e testes.
- O hook depende de detalhes internos do PySpark (módulos `pyspark.sql.session` e `pyspark.sql.classic.session`).

### Riscos
- Mudanças de API do PySpark podem quebrar o hook silenciosamente. Mitigação observada: erros são registrados e avisados uma vez; a instalação tem timeout (`ENSURE_WAIT`).

## Validação
- **Evidência no código:** `backend/src/notisbook/kernels/service.py` (`_install_display`, `ENSURE_CHECK`), `backend/src/notisbook/kernels/sql_cell.py` (`MODULE_NAME = "_notisbook_display"`), `backend/src/notisbook/kernels/catalog_hook.py` (`MODULE_NAME = "_notisbook_catalog"`), `backend/src/notisbook/catalog/managed.py` (código reaproveitado no kernel via `inspect.getsource`).
- **Como confirmar:** `grep -n "silent=True" backend/src/notisbook/kernels/service.py`; ler as docstrings de `sql_cell.py` e `catalog_hook.py`.

## Notas de Implementação
- Células DuckDB usam uma conexão em memória por kernel, com instalação automática de extensões desligada para manter o kernel offline.
- A versão do DuckDB no ambiente Spark é fixada em `DUCKDB_VERSION` (`spark/installer.py`).

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
