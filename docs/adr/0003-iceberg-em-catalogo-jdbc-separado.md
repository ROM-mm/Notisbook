# ADR-0003: Iceberg em catálogo JDBC próprio, separado do spark_catalog

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Delta e Iceberg precisam coexistir na mesma SparkSession.

## Decisão
Iceberg usa um catálogo nomeado `iceberg` (`JdbcCatalog` sobre o `catalog.db`) e o `spark_catalog` fica reservado ao Delta. O backend cria as tabelas internas do Iceberg (`init-catalog-tables false`) e lê/escreve esse formato numa camada isolada.

Motivação declarada em comentário: `SparkSessionCatalog` e `DeltaCatalog` não podem dividir o slot do catálogo de sessão; a criação das tabelas pelo backend evita conflito de snapshot (BUSY_SNAPSHOT).

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Delta e Iceberg na mesma sessão.
- Painel e exclusão de schema funcionam sem Spark.

### Negativas
- Tabelas Iceberg exigem o prefixo `iceberg.`.
- O backend depende do formato interno do `JdbcCatalog`.

### Riscos
- Mudança de esquema do JdbcCatalog numa versão nova. Mitigação: camada `catalog/iceberg_jdbc.py` e erro `unsupported_iceberg_catalog_schema`.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/bundles.py:192-217`, `backend/src/notisbook/catalog/iceberg_jdbc.py:1-7`
- **Como confirmar:** `grep -n JdbcCatalog backend/src/notisbook/spark/bundles.py`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
