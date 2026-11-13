# ADR-0004: Iceberg em catálogo JDBC próprio, separado do spark_catalog

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Os ambientes Spark do Notisbook suportam Delta, Iceberg e Hudi na mesma sessão. O slot do catálogo de sessão (`spark_catalog`) só pode ter uma implementação.

## Decisão
- `spark_catalog` usa o `DeltaCatalog`.
- Iceberg vive em um catálogo nomeado `iceberg` (`org.apache.iceberg.spark.SparkCatalog`, `type jdbc`), apontando via `jdbc:sqlite:` para o mesmo `catalog.db`, com warehouse em `<home>/warehouse/iceberg` e `jdbc.schema-version V1`.
- O backend cria as tabelas `iceberg_tables` e `iceberg_namespace_properties` (DDL que replica o `JdbcCatalog` do Iceberg 1.10.1 com `IF NOT EXISTS`) e o Spark é configurado com `jdbc.init-catalog-tables false`.
- O driver `sqlite-jdbc` entra no classpath do driver JVM (`spark.driver.extraClassPath`), pois o catálogo JDBC o localiza via `DriverManager`.
- O backend lê e escreve o catálogo Iceberg diretamente do SQLite e dos `metadata.json`, sem Spark (`catalog/iceberg_jdbc.py`).

Motivação documentada no código: a docstring de `render_spark_defaults` afirma que `SparkSessionCatalog` e `DeltaCatalog` não podem dividir o slot do catálogo de sessão; o comentário sobre `init-catalog-tables false` afirma que a inicialização do próprio catálogo fixa um snapshot de leitura na conexão SQLite em pool e quebra o commit seguinte após escrita externa (`BUSY_SNAPSHOT`).

## Alternativas Consideradas
O comentário do código menciona `SparkSessionCatalog` do Iceberg no slot de sessão como inviável junto ao `DeltaCatalog`. Outras alternativas não foram identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Delta, Iceberg e Hudi coexistem na mesma `SparkSession`.
- Um único arquivo (`catalog.db`) concentra os dois catálogos, sem serviço externo.
- O painel de catálogo funciona sem kernel ativo.

### Negativas
- Tabelas Iceberg precisam ser qualificadas pelo catálogo `iceberg`.
- O backend depende do formato interno (não público) do `JdbcCatalog`; trocar a versão do Iceberg na matriz exige revisar leitura e escrita.
- `NOTISBOOK_HOME` não pode conter `?`, pois quebraria a URL JDBC (`UnsupportedHome`).

### Riscos
- Mudança de schema do `JdbcCatalog` em versões futuras. Mitigação observada: verificação de colunas (`_check_schema`) e degradação apenas do catálogo `iceberg` (`unsupported_iceberg_catalog_schema`), sem afetar o restante do painel.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/bundles.py` (`render_spark_defaults`, `catalog_uri`, `SQLITE_JDBC`), `backend/src/notisbook/catalog/store.py` (`_ICEBERG_DDL`), `backend/src/notisbook/catalog/iceberg_jdbc.py`.
- **Como confirmar:** `grep -n "spark.sql.catalog" backend/src/notisbook/spark/bundles.py`; o smoke test em `backend/src/notisbook/spark/installer.py` (`SMOKE_SCRIPT`) executa `SHOW NAMESPACES IN iceberg`.

## Notas de Implementação
- Os comentários marcam a dependência da versão 1.10.1 do Iceberg; a entrada `4.1` da matriz usa Iceberg 1.12.0, o que torna a revisão indicada nos comentários relevante.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
