# ADR-0002: Catálogo de tabelas persistente em SQLite, sem metastore Hive

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O catálogo de uma SparkSession some quando a sessão termina; o painel Data precisa listar tabelas sem abrir Spark.

## Decisão
O Spark roda com `spark.sql.catalogImplementation=in-memory` e o registro persistente fica em `~/.notisbook/catalog.db` (SQLite, WAL), com tabelas `nb_*` para Delta/Parquet. Um módulo oculto injetado em cada kernel (`_notisbook_catalog`) sincroniza a sessão com o `catalog.db`; o backend é dono do esquema e das migrações.

Motivação declarada em comentário: o catálogo em memória mantém o metastore Hive embutido fora da pasta do notebook, e o registro persistente vive no `catalog.db`.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Tabelas sobrevivem ao fim da sessão.
- Painel Data lê o catálogo sem iniciar JVM.

### Negativas
- Três escritores no mesmo arquivo (backend, kernels, JdbcCatalog do Iceberg) exigem locks e `busy_timeout`.
- Recursos do Hive não estão disponíveis; `enableHiveSupport()` desliga a sincronização.

### Riscos
- Contenção de escrita no SQLite. Mitigação: `BEGIN IMMEDIATE` e `busy_timeout` (5 s backend, 10 s JDBC).

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/bundles.py:179-189`, `backend/src/notisbook/catalog/store.py`, `backend/src/notisbook/kernels/catalog_hook.py:1-13`
- **Como confirmar:** `grep -n catalogImplementation backend/src/notisbook/spark/bundles.py`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
