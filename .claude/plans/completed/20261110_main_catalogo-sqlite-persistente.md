# Catálogo persistente em SQLite (Delta, Parquet, Iceberg)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 14:48:30 -0300
Modificação: 2026-11-10 16:39:10 -0300
Finalização: 2026-11-10 16:39:10 -0300

## Objetivo

Painel Catalog mostra schemas, tabelas (Delta, Parquet, Iceberg), tipo MANAGED/EXTERNAL e colunas **sem SparkSession**, a partir de `~/.notisbook/catalog.db`. Tabelas criadas em qualquer notebook persistem entre notebooks e reinícios, e numa sessão nova ficam acessíveis já na linha seguinte ao `getOrCreate()` (`spark.table`, `spark.read.table`, SQL, INSERT/MERGE, `saveAsTable` append).

Por que este caminho: Hive Metastore não suporta SQLite; Derby foi vetado pelo operador; catálogo próprio em JVM exige build que o projeto não tem. Um `catalog.db` com dois modelos separados — `iceberg_*` (Iceberg JdbcCatalog, fonte de verdade das tabelas Iceberg) e `nb_*` (registro do Notisbook, fonte de verdade de Delta/Parquet) — mantido por um módulo oculto no kernel que hidrata a sessão no `getOrCreate` e reconcilia após cada célula. O backend é dono do DDL e lê os dois sem Spark. Só o Notisbook lê/escreve o arquivo; tudo é criado via notebooks do Notisbook.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `catalog.db` na partida do backend: WAL, migração `nb_*` por `user_version`, DDL Iceberg V1 com `IF NOT EXISTS` (+`iceberg_type`); `METASTORE_DIR` sai do `ensure_home` | python-engineer | — | 1 | escrita |
| T2 | Bundle/conf Spark: `SQLITE_JDBC` em `Bundle.driver_artifacts` → `spark.driver.extraClassPath`; `revision=3` nas 3 entradas; catálogo `iceberg` type jdbc (uri `jdbc:sqlite:<home>/catalog.db`, warehouse `<home>/warehouse/iceberg`, `jdbc.schema-version V1`); `spark.sql.catalogImplementation in-memory`; Derby removido; smoke de instalação com `SHOW NAMESPACES IN iceberg` em SQLite temporário; `_ensure_spark_defaults` no start do kernel só com todos os jars presentes; recusar `NOTISBOOK_HOME` com `?` | python-engineer | T1 | 2 | escrita |
| T3 | API sem sessão `GET /api/catalog` e `GET /api/catalog/columns` (`catalog/registry.py`, `catalog/iceberg_jdbc.py` com leitura degradável); remover rota `/api/sessions/{id}/catalog` (+`/columns`) e a operação de introspecção de catálogo do kernel, preservando o que o painel Variables usa | python-engineer | T1 | 3 | escrita |
| T4 | Módulo oculto `_notisbook_catalog` (`kernels/catalog_hook.py`), instalado em `_install_display`: gancho no import em `Builder.getOrCreate`/`stop`, hidratação na mesma chamada, `pre_run_cell` por `generation`, `post_run_cell` reconciliando criação/alteração/RENAME/DROP (gerenciada apaga arquivos só dentro de `warehouse/spark`), aviso de ambiente desatualizado, aviso e desligamento com Hive | python-engineer | T1,T2 | 4 | escrita |
| T5 | Frontend: CatalogSection lê `/api/catalog` sem sessão, mostra formato/tipo/colunas, relê após célula voltar a idle, foco e botão; aviso `outdated` ("reinstall") no painel de versões Spark | python-engineer | T3 | 5 | escrita |
| T6 | Painel exibe o rótulo `spark` para o catálogo `spark_catalog` (só exibição; API e nomes Spark inalterados) — ampliação de escopo pedida pelo operador após o teste | python-engineer | T5 | 6 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3
- Wave 4 (serial, escrita): T4
- Wave 5 (serial, escrita): T5
- Wave 6 (serial, escrita): T6

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | `catalog.db` único com `iceberg_*` e `nb_*` separados | SQLite como fonte persistente única, sem serviço externo; modelos não se misturam | `notisbook-sqlite-catalog.md`; parecer software-architect | Hive+SQLite (sem suporte oficial); Derby (vetado pelo operador); catálogo JVM próprio (sem build JVM no projeto) |
| D2 | Hidratar no `getOrCreate` via gancho no import de `pyspark.sql.session` | Tabelas disponíveis na linha seguinte da mesma célula | IPython não dispara `pre/post_run_cell` em execute silencioso (`interactiveshell.py:3253-3254`, parecer); usuário cria a sessão (`sql_cell.py:279-282`) | Só `post_run_cell` (falha no import+getOrCreate na mesma célula) |
| D3 | Backend cria o DDL Iceberg V1 com `IF NOT EXISTS` na partida | DDL do JdbcCatalog não tem `IF NOT EXISTS` → corrida entre kernels | inspeção do jar `iceberg-spark-runtime-3.5_2.12-1.10.1.jar` (parecer) | Cada JVM inicializa (`jdbc.init-catalog-tables`) |
| D4 | Backend lê Iceberg via SQLite + `metadata.json`, sem pyiceberg | Evita dependências pesadas e DDL concorrente; filtra views por `iceberg_type`; leitura degrada sem quebrar o painel | parecer software-architect | pyiceberg `SqlCatalog`; kernel projetando Iceberg em `nb_*` |
| D5 | `sqlite-jdbc` em `spark.driver.extraClassPath`, fora de `spark.jars` | JdbcCatalog usa `DriverManager`; driver no classloader do `spark.jars` pode não ser visto | `DriverManager.getConnection` no jar Iceberg (parecer); efeito no pyspark `unverified` → smoke T2 | `spark.jars` |
| D6 | Ambientes já instalados: reinstalar (revision 3); conf ajustada no start só com jar presente; kernel continua offline | Kernel não baixa nada em runtime | premissa do bundle (`installer.py:412-466`) | Baixar jar no start do kernel |
| D7 | Warehouse Iceberg continua `<home>/warehouse/iceberg`; catálogo começa vazio, tabelas hadoop antigas não migradas | Decisão do operador | sem evidência — preferência do operador | `warehouse/iceberg_jdbc` (sugerido pelo architect) |
| D8 | Painel só com catálogo persistente; rota de catálogo por sessão removida | Decisão do operador; evita código morto | sem evidência — preferência do operador | Seção "Session (temporary)" com temp views |
| D9 | Derby desligado (`catalogImplementation in-memory`, sem `derby.system.home`, sem `metastore/`) | Evitar duas fontes de verdade | `bundles.py:160-162`, `config.py:32` | Manter Derby/Hive |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Backend compila | `python -m compileall backend/src` sem erro | constraint |
| T1 | `catalog.db` criado na partida com WAL e tabelas dos dois modelos | após subir o backend: `sqlite3 ~/.notisbook/catalog.db "PRAGMA journal_mode; PRAGMA user_version; .tables"` → `wal`, valor > 0, e `iceberg_namespace_properties iceberg_tables nb_meta nb_namespaces nb_tables` | feature |
| T1 | Tabela Iceberg em V1 | `sqlite3 ~/.notisbook/catalog.db "PRAGMA table_info(iceberg_tables)"` inclui `iceberg_type` | feature |
| T1 | Metastore fora do `ensure_home` | `grep -n METASTORE_DIR backend/src/notisbook/config.py` sem resultado | constraint |
| T2 | Sem configuração Derby | `grep -n "derby" backend/src/notisbook/spark/bundles.py` só retorna loggers log4j | constraint |
| T2 | Revisão do bundle sobe | `grep -n "revision=3" backend/src/notisbook/spark/bundles.py` retorna as 3 entradas | feature |
| T2 | Conf do ambiente reinstalado aponta Iceberg para o SQLite | `spark-defaults.conf` do ambiente 3.5.9 reinstalado contém `spark.sql.catalog.iceberg.type jdbc`, `spark.sql.catalog.iceberg.uri jdbc:sqlite:<home>/catalog.db`, `spark.sql.catalog.iceberg.jdbc.schema-version V1`, `spark.sql.catalog.iceberg.warehouse <home>/warehouse/iceberg`, `spark.sql.catalogImplementation in-memory`, `spark.driver.extraClassPath` com `sqlite-jdbc-*.jar`; e a linha `spark.jars` não contém `sqlite-jdbc` | feature |
| T2 | JdbcCatalog não inicializa tabelas (evita SQLITE_BUSY_SNAPSHOT com escritas concorrentes no catalog.db); contorno no hook removido | `grep -n "init-catalog-tables false" backend/src/notisbook/spark/bundles.py` presente e `grep -n "disable_catalog_init" backend/src/notisbook/kernels/catalog_hook.py` vazio; smoke de 2 kernels (INSERT Iceberg × saveAsTable) sem `database is locked` | bugfix |
| T2 | Smoke de instalação exercita o driver | instalação do 3.5.9 imprime `bundle-smoke-ok` após `SHOW NAMESPACES IN iceberg` contra SQLite temporário | feature |
| T2 | Ambiente revision 2 sem o jar não tem conf alterada | `shasum <env>/spark-conf/spark-defaults.conf` igual antes e depois de iniciar um kernel | constraint |
| T3 | Catálogo disponível sem kernel | sem kernel ativo, `curl -s "http://127.0.0.1:<port>/api/catalog?token=<token>"` → `status: ok` com `spark_catalog` e `iceberg` | feature |
| T3 | Colunas sem kernel e 404 para inexistente | `curl` em `/api/catalog/columns?catalog=iceberg&database=lab&table=x` lista colunas; tabela inexistente → HTTP 404 | feature |
| T3 | Leitura Iceberg degrada sem quebrar | `iceberg_tables` com schema inesperado (cópia de teste do db) → só o catálogo `iceberg` vem com `error`, `spark_catalog` intacto | feature |
| T3 | Rota por sessão removida | `grep -rn "sessions/{session_id}/catalog" backend/src` sem resultado | constraint |
| T4 | Tabelas criadas no notebook entram no registro | smoke 3.5.9: Delta gerenciada (`saveAsTable`), Parquet externa (`path=`), `CREATE TABLE ... USING delta` e `iceberg.lab.x` → `sqlite3 ~/.notisbook/catalog.db "select namespace,table_name,format,table_type from nb_tables"` lista as 3 não-Iceberg com tipo correto e `select table_namespace,table_name from iceberg_tables` tem `lab|x` | feature |
| T4 | Sessão nova acessa as tabelas na mesma célula do `getOrCreate` | kernel novo, mesma célula: `getOrCreate()` seguido de `spark.table`, `spark.read.table`, `spark.sql` SELECT/INSERT/MERGE (Delta) e `saveAsTable(mode="append")` executam sem exceção | feature |
| T4 | DROP respeita gerenciada/externa; RENAME preserva tipo | smoke: `DROP` da gerenciada remove a pasta em `warehouse/spark`; `DROP` da externa mantém arquivos (`ls <path>`); `ALTER TABLE ... RENAME` mantém `table_type` em `nb_tables` | feature |
| T4 | `stop()` não apaga registro | smoke: `spark.stop()` + novo `getOrCreate()` → `select count(*) from nb_tables` igual antes e depois | constraint |
| T4 | Concorrência entre kernels | smoke: 2 kernels em paralelo (INSERT Iceberg + `saveAsTable` em tabelas distintas) sem `database is locked` na saída | feature |
| T4 | Tempo de hidratação medido | smoke registra o tempo do `getOrCreate` com 50 tabelas Delta (número reportado em `evidência`) | feature |
| T4 | Catálogo corrente ≠ `spark_catalog` não apaga registro nem arquivos (review blocker) | `grep -n "spark_catalog" backend/src/notisbook/kernels/catalog_hook.py` mostra listagem/identificadores qualificados; smoke: célula `spark.sql("USE iceberg")` + célula seguinte → `select count(*) from nb_tables` igual e pastas MANAGED existem (`ls`) | bugfix |
| T2 | Smoke de instalação passa com `init-catalog-tables false` (review major) | instalação nova do 3.5.9 em home isolado imprime `[validate] bundle-smoke-ok` | bugfix |
| T2 | `SQLITE_JDBC` definido uma vez (review minor) | `grep -c "^SQLITE_JDBC = " backend/src/notisbook/spark/bundles.py` → `1` | bugfix |
| T4 | Refresh profundo só com SQL de DDL explícito (review minor) | `grep -n "DEEP_RE" backend/src/notisbook/kernels/catalog_hook.py` mostra padrões com `\\b` e `TABLE` (ex.: `DROP\\s+TABLE`); célula com `df.dropna()` não dispara refresh profundo (smoke) | bugfix |
| T4 | Prefixo do warehouse Iceberg comparado com separador (review minor) | `grep -n "ICEBERG_WAREHOUSE" backend/src/notisbook/kernels/catalog_hook.py` mostra comparação com `/` final ou `commonpath`; tabela Delta em `warehouse/iceberg_raw/` é registrada (smoke) | bugfix |
| T4 | Sem banners de separador no hook (review minor) | `grep -n "# ----" backend/src/notisbook/kernels/catalog_hook.py` vazio | bugfix |
| T4 | DROP legítimo de todas as tabelas conhecidas (≥2) é aplicado; trava só quando a ausência não é confirmada (review major r2) | smoke: célula `DROP TABLE a; DROP TABLE b` (únicas conhecidas) → `select count(*) from nb_tables` = 0 e pasta MANAGED removida; `DROP DATABASE x CASCADE` com todas as conhecidas → linhas removidas; listagem simulada sem as tabelas que ainda existem (`tableExists` True) → linhas mantidas | bugfix |
| T5 | Frontend compila | `cd frontend && npm run typecheck` sem erro | constraint |
| T5 | Painel usa a API sem sessão | `grep -n "/api/catalog" frontend/src/api/catalog.ts` presente e `grep -rn "sessions/.*catalog" frontend/src` sem resultado | feature |
| T5 | Catálogo vazio exibe estado vazio, sem erro | com `catalog.db` recém-criado, `GET /api/catalog` → `status: ok` sem tabelas; `grep -rn "No tables yet" frontend/src/components/data` retorna o estado vazio do CatalogSection | feature |
| T5 | Aviso de ambiente desatualizado | `grep -rn "outdated" frontend/src` retorna o uso no painel de versões Spark com texto em inglês contendo "reinstall" | feature |
| T6 | Painel mostra `spark` no lugar de `spark_catalog`; API segue devolvendo `spark_catalog` | `grep -rn '"spark"' frontend/src/components/data/CatalogSection.tsx` mostra o mapeamento de rótulo; `curl /api/catalog` ainda traz `"name":"spark_catalog"`; `npm run typecheck` exit 0 | feature |

## Arquivos previstos
- `backend/src/notisbook/catalog/__init__.py` — T1
- `backend/src/notisbook/catalog/store.py` — T1
- `backend/src/notisbook/config.py` — T1
- `backend/src/notisbook/app.py` — T1
- `backend/src/notisbook/__main__.py` — T1
- `backend/src/notisbook/spark/bundles.py` — T2
- `backend/src/notisbook/spark/installer.py` — T2
- `backend/src/notisbook/kernels/service.py` — T2, T3, T4
- `backend/src/notisbook/catalog/registry.py` — T3
- `backend/src/notisbook/catalog/iceberg_jdbc.py` — T3
- `backend/src/notisbook/api/catalog.py` — T3
- `backend/src/notisbook/kernels/introspect.py` — T3
- `backend/src/notisbook/kernels/catalog_hook.py` — T2, T4
- `frontend/src/api/catalog.ts` — T5
- `frontend/src/state/catalog.ts` — T5
- `frontend/src/components/data/CatalogSection.tsx` — T5, T6
- `frontend/src/api/types.ts` — T5
- `frontend/src/components/data/DataPanel.module.css` — T5
- `frontend/src/components/` (painel de versões Spark) — T5

## Fora de escopo
- Importar tabelas Iceberg hadoop antigas de `warehouse/iceberg` e pastas legadas de `warehouse/spark` — decisão do operador (começa vazio).
- CSV/JSON/ORC/Hudi e views persistentes no registro — não pedidos; aviso por sessão.
- Tabelas criadas fora do Notisbook, Spark Connect, catálogos além de `spark_catalog`/`iceberg`.
- Temp views no painel — decisão do operador (D8).
- Testes automatizados versionados — não pedidos; verificação por smokes avulsos no scratchpad.
- Smoke em 3.5.0–3.5.2 e 4.1 — sem ambiente; reportado como `unverified`.
- **Documentação de produto** — nenhum README/ARCHITECTURE/doc de módulo é tocado; a proposta `notisbook-sqlite-catalog.md` fica como está. ADR só se o operador pedir.

## Não mexer
- `~/.notisbook/metastore/` e pastas existentes em `~/.notisbook/warehouse/` — não apagar nem migrar.
- Sonda do painel Variables (`api/variables.py` e o execute silencioso que ele usa).
- Célula SQL continua usando a sessão ATIVA, nunca `getOrCreate` (`kernels/sql_cell.py`).
- `log4j2.properties` / `_ensure_log4j2` e o `RegexFilter` de ruído Spark.
- Escopo visual `.neo`; `global.css` intocado; UI só em inglês.

## Riscos declarados
- Para o Spark toda tabela hidratada é EXTERNAL; semântica de gerenciada no DROP é garantida pelo Notisbook.
- Custo do `getOrCreate` cresce com o nº de tabelas Delta.
- Tabela Iceberg nova com o mesmo ns/nome de uma antiga hadoop compartilha a pasta em `warehouse/iceberg`.
- `unverified` (sem Context7 na sessão): versão/sha256/pragmas do sqlite-jdbc, `extraClassPath` via spark-defaults, `RECOVER PARTITIONS` em catálogo em memória, Delta `createTable(path=)`, Parquet gerenciada com overwrite.
- `extraClassPath` definido pelo usuário no builder remove o driver SQLite.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 137947 | 79200 |
| 0 | software-architect | OK | 502032 | 118317 |
| 1 | python-engineer | OK | 170665 | 48800 |
| 2 | python-engineer | OK | 214007 | 86456 |
| 3 | python-engineer | OK | 196903 | 99342 |
| 4 | python-engineer | OK | 946470 | 183068 |
| 5 | python-engineer | OK | 168505 | 85148 |
| 6 | code-review (skill) | ajustes necessários | 186936 | 114821 |
| 6 | plan-auditor | OK | 55214 | 32748 |
| 7 | python-engineer | OK | 735785 | 141276 |
| 8 | code-review (skill) | ajustes necessários | 102615 | 103836 |
| 8 | plan-auditor | OK | 78745 | 49971 |
| 9 | python-engineer | OK | 573360 | 49035 |
| 10 | code-review (skill) | aprovar | 86173 | 115545 |
| 10 | plan-auditor | OK | 73758 | 50835 |
| 11 | python-engineer | OK | 16894 | 31045 |
| 12 | code-review (skill) | aprovar | 35841 | 65063 |
| 12 | plan-auditor | OK | 55334 | 45193 |
<!-- effort-ledger:end -->
