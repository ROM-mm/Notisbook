# ADR-0003: Catálogo de tabelas persistente em SQLite, sem metastore Hive

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Tabelas Delta, Parquet e Hudi criadas nos notebooks precisam continuar visíveis entre sessões e entre kernels concorrentes. Por padrão, o Spark usaria um metastore Hive embutido gravado no diretório de trabalho do kernel (a pasta do notebook).

## Decisão
O catálogo persistente é um arquivo SQLite único, `<NOTISBOOK_HOME>/catalog.db`, criado e migrado pelo backend na partida (`ensure_catalog_db`, chamado em `__main__.py` antes de qualquer kernel):
- Tabelas do registro do Notisbook `nb_namespaces`, `nb_tables` e `nb_meta`, versionadas por `PRAGMA user_version` com migrações sequenciais (`_NB_MIGRATIONS`).
- Modo WAL, transações explícitas `BEGIN IMMEDIATE` e `busy_timeout` para concorrência entre backend e kernels.
- No Spark, o catálogo de sessão fica em memória (`spark.sql.catalogImplementation in-memory`) e o warehouse padrão é fixado em `<home>/warehouse/spark`; a sessão é hidratada a partir do registro pelo hook do kernel.

A docstring de `render_base_defaults` (`spark/bundles.py`) registra o efeito pretendido: manter o metastore Hive embutido fora da pasta do notebook, já que "o registro persistente vive em `catalog.db`". Fora isso, a motivação histórica não foi recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Nenhuma pasta `metastore_db`/`spark-warehouse` aparece nas pastas de notebooks.
- Um único arquivo concentra o catálogo e pode ser lido pelo backend sem Spark (painel de catálogo em `api/catalog.py`).
- Migrações idempotentes e seguras com partidas concorrentes.

### Negativas
- O catálogo `spark_catalog` aceita só os formatos permitidos pelo `CHECK` (`delta`, `parquet`, `hudi`); outros exigem migração.
- O SQLite não altera `CHECK`, então mudanças de formato exigem recriar a tabela (como na migração 2).

### Riscos
- Contenção de escrita entre vários kernels. Mitigação observada: WAL, `busy_timeout` e `nb_meta.generation` para detectar escritas de outros kernels.

## Validação
- **Evidência no código:** `backend/src/notisbook/catalog/store.py` (`CATALOG_DB`, `_NB_MIGRATIONS`, `ensure_catalog_db`), `backend/src/notisbook/__main__.py` (chamada a `ensure_catalog_db`), `backend/src/notisbook/spark/bundles.py` (`render_base_defaults`), `backend/src/notisbook/kernels/catalog_hook.py`.
- **Como confirmar:** `grep -n "catalogImplementation" backend/src/notisbook/spark/bundles.py`; ler `_NB_MIGRATIONS` em `catalog/store.py`.

## Notas de Implementação
- O backend é o único que cria/altera o schema do `catalog.db` (docstring de `catalog/store.py`).
- A remoção de arquivos de tabelas MANAGED é restrita ao warehouse por `managed_table_dir` (`catalog/managed.py`).
- O mesmo arquivo hospeda as tabelas do catálogo Iceberg, tratadas em ADR-0004.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
