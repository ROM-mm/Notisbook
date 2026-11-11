# Menus de schema no Catalog e Delete Folder no Files

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 16:57:40 -0300
Modificação: 2026-11-10 19:09:12 -0300
Finalização: 2026-11-10 19:09:12 -0300

## Objetivo

Clique direito no painel Data, sem SparkSession: no nome do catálogo (`spark`/`iceberg`) → **Create Schema…**; no schema → **Delete Schema…** em cascata com confirmação (remove schema e tabelas do catálogo, apaga pastas das tabelas MANAGED, mantém arquivos das EXTERNAL), nos dois catálogos; em Files, numa pasta → **Delete Folder…** com confirmação. Sem menu em tabela.

Por que assim: o backend passa a escrever no `catalog.db` (registro `nb_*` e formato interno do Iceberg JdbcCatalog 1.10.1, reproduzindo o SQL dele), commit antes de apagar arquivos (órfão recuperável é melhor que catálogo apontando para dado apagado). Pré-requisito: o hook do kernel hoje roda `DROP DATABASE` na sessão quando um schema some do registro, e o InMemoryCatalog do Spark 3.5.9 apaga `<wh>/<db>.db` recursivamente (inclusive EXTERNAL) — precisa ser corrigido antes da exclusão existir.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Salvaguarda de pasta MANAGED numa fonte única (`catalog/managed.py::managed_table_dir`), injetada no template do hook; `delete_managed` passa a usá-la sem mudar comportamento | python-engineer | — | 1 | escrita |
| T2 | Hook: `sync_registry` só faz `DROP DATABASE` na sessão se a pasta do db não existe/está vazia; senão tombstone (sessão deixa de reconsiderá-lo e `reconcile` não o recria no registro) | python-engineer | T1 | 2 | escrita |
| T3 | Backend: escrita em `registry.py`/`iceberg_jdbc.py`, `catalog/schemas.py`, rotas `POST /api/catalog/schemas`, `GET /api/catalog/schemas/preview`, `DELETE /api/catalog/schemas` (etag, validação de nome, `default` recusado, filhos Iceberg recusados, `gc.enabled=false` mantém arquivos, 409 `kernel_busy`) | python-engineer | T1,T2 | 3 | escrita |
| T4 | Backend: `fs_safety` (predicado protegido + `remove_tree`) reaproveitado por `NotebookStore.delete` sem mudar comportamento; rota `DELETE /api/fs/dir` com allowlist | python-engineer | — | 4 | escrita |
| T5 | Front Catalog: `ConfirmDialog`, `CreateSchemaDialog`, menus de catálogo e schema, clientes da API, árvore sempre visível com `data`, refresh e limpeza de `expanded` | python-engineer | T3 | 5 | escrita |
| T6 | Front Files: item "Delete Folder…" com confirmação, `forget`/`reload` no store, reload da árvore de notebooks quando sob a raiz | python-engineer | T4 | 6 | escrita |

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
| D1 | Backend escreve em `iceberg_*` com o mesmo SQL do JdbcCatalog 1.10.1 (create = linha `exists=true`; drop = DELETE de tabelas/views do namespace e depois das propriedades) | Requisito "sem SparkSession"; acoplamento isolado em `iceberg_jdbc.py` com versão fixada na MATRIX | `javap` em `iceberg-spark-runtime-3.5_2.12-1.10.1.jar` (`JdbcCatalog.createNamespace/dropNamespace/dropTable`, `JdbcUtil`) — parecer do architect | JVM auxiliar/SparkSession (viola requisito); pyiceberg (descartado no plano anterior) |
| D2 | Ordem: `BEGIN IMMEDIATE` → valida/etag → DELETE linhas → COMMIT → apaga pastas MANAGED → `rmdir` não recursivo da pasta do schema se vazia; falha de arquivo volta em `files_kept`/`folder_kept`, não como 5xx | Órfão recuperável > catálogo apontando para nada; nenhum I/O de arquivo com lock aberto | mesma ordem de `apply_changes` no hook | rm antes do commit |
| D3 | Cascade apaga só pastas MANAGED; EXTERNAL mantém arquivos (difere do Spark, que faz `rm -rf <db>.db`) | Pedido do operador (1=b) | `InMemoryCatalog.dropDatabase` → `fs.delete(location, true)` em spark-catalyst 3.5.9 | idêntico ao Spark |
| D4 | Hook nunca roda `DROP DATABASE` destrutivo no sync (tombstone quando a pasta não está vazia) | Evita perda de EXTERNAL e ressurreição do schema | `catalog_hook.py:426-431` e `:628` | dropar sempre / nunca dropar |
| D5 | Etag (sha256 das linhas do namespace) entre preview e delete | Contagem não detecta troca de tabelas | sem evidência — desenho do architect | só contagem |
| D6 | Nome de schema `^[A-Za-z_][A-Za-z0-9_]{0,127}$`, colisão sem caixa; `spark` grava em minúsculas | `.` separa níveis no JdbcCatalog; SessionCatalog normaliza minúsculas; APFS sem caixa | `JdbcUtil.namespaceToString` | aceitar qualquer nome entre crases |
| D7 | Delete Folder com allowlist: só dentro da home ou `/Volumes/…`; recusa home/ancestrais, `~/.notisbook` e tudo dentro, pastas ocultas, raiz dos notebooks e ancestrais, pasta com notebook em kernel ativo, pasta que é/contém/está dentro de location de tabela registrada; symlink remove só o link | Files alcança o disco inteiro; recusa por padrão | `notebooks/store.py:230-251`, `api/contents.py:94-106` | denylist de pastas de sistema |
| D8 | Delete schema recusa com 409 `kernel_busy` se algum kernel estiver executando | Evita job recriando arquivos órfãos durante o delete | sem evidência — recomendação do architect, adotada como default (operador mandou implementar sem responder; reverter é trivial) | sem trava |
| D9 | Rótulos Title Case: "Create Schema…", "Delete Schema…", "Delete Folder…" | Consistência com "Copy Path" | `FileTree.tsx` | "Create schema" |
| D10 | Sem autoria de smoke novo (o operador não autorizou estender o roteiro); verificação por `curl`, `sqlite3`, `ls` e comandos pontuais; `run_all.sh` existente só como regressão | Política de não-autoria de testes | sem evidência — decisão de política | estender `run_all.sh` |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Salvaguarda numa fonte única, injetada no hook | `grep -n "managed_table_dir" backend/src/notisbook/catalog/managed.py backend/src/notisbook/kernels/catalog_hook.py` acha definição e uso; `python -c "import inspect,notisbook.catalog.managed as m;print(inspect.getsource(m.managed_table_dir)[:40])"` no `.venv` funciona | refactor |
| T1 | DROP de MANAGED segue igual | `bash <scratchpad>/smokes/run_all.sh` exit 0 (regressão, sem alteração do script) | constraint |
| T2 | Schema removido do registro com notebook aberto não apaga arquivos nem volta ao registro | comando pontual com Spark 3.5.9 real: kernel com schema `x` hidratado e EXTERNAL em `<wh>/spark/x.db/ext`; apagar linhas de `x` + `generation+1` via `sqlite3`; rodar célula → `ls <wh>/spark/x.db/ext` existe e `sqlite3 catalog.db "select count(*) from nb_namespaces where namespace='x'"` = 0 | bugfix |
| T2 | Com pasta vazia o schema sai da sessão | mesmo cenário com `x.db` vazia → `SHOW NAMESPACES` na sessão não lista `x` | feature |
| T3 | Criar schema `spark` | `curl -X POST /api/catalog/schemas -d '{"catalog":"spark_catalog","name":"Sales"}'` → 201 `"name":"sales"`; repetir com `SALES` → 409 `schema_exists`; `a.b` → 400 `invalid_name`; `global_temp` → 400 | feature |
| T3 | Criar schema `iceberg` legível pelo Spark | POST iceberg `x` → `sqlite3 catalog.db "select * from iceberg_namespace_properties where namespace='x'"` = `iceberg|x|exists|true`; `spark.sql("SHOW NAMESPACES IN iceberg")` lista `x` e `CREATE TABLE iceberg.x.t (id INT)` funciona | feature |
| T3 | Preview + etag | `GET /api/catalog/schemas/preview` traz `tables/managed/external/etag`; DELETE com etag antigo → 409 `catalog_changed` | feature |
| T3 | Delete schema `spark` | DELETE com 1 MANAGED + 1 EXTERNAL fora do warehouse → pasta MANAGED some (`ls`), EXTERNAL fica, `nb_meta.generation` +1, linhas de `x` somem | feature |
| T3 | Delete schema `iceberg` | DELETE com tabela MANAGED → pasta some; `iceberg_tables`/`iceberg_namespace_properties` sem `x`; `SHOW NAMESPACES IN iceberg` não lista `x`; tabela com `gc.enabled=false` volta em `files_kept` | feature |
| T3 | Recusas | `default` → 409 `cannot_drop_default`; namespace `x.y` presente → 409 `has_child_namespaces`; kernel executando → 409 `kernel_busy` | feature |
| T3 | Escrita do backend não quebra commit Iceberg em sessão aberta | sessão Iceberg aberta faz commit na própria tabela após DELETE do backend em outro namespace → sem `database is locked` | constraint |
| T4 | Delete folder com allowlist | `curl -X DELETE "/api/fs/dir?path=..."`: `$HOME` → 403; `$NOTISBOOK_HOME/warehouse` → 403; `$HOME/.config` (existente) → 403; `/opt` (existente) → 403; location de tabela EXTERNAL → 409 `contains_catalog_tables`; pasta com notebook em kernel → 409; `$HOME/tmpdata/a` → 204 e some; symlink → só o link | feature |
| T4 | Delete de Notebooks inalterado | `curl -X DELETE /api/contents/<dir>` mantém 204/409/400 nos mesmos casos de antes | constraint |
| T3 | Pasta em uso detectada sem diferenciar maiúsculas (APFS) — review major | `grep -n "casefold\|fold=True" backend/src/notisbook/catalog/schemas.py` na verificação de pasta em uso; comando pontual: Iceberg `Foo.t` e `foo.t` apontando à mesma pasta (ou EXTERNAL de outro schema em `…/X.db/t`) → DELETE de `foo`/`x` devolve `files_kept` `in_use` e a pasta continua (`ls`) | bugfix |
| T3 | Pasta MANAGED do spark amarrada a `<root>/<schema>.db/<t>` — review minor | comando pontual: linha MANAGED de `x` com location em `<root>/t` → DELETE devolve `files_kept` `outside_warehouse` e a pasta continua | bugfix |
| T3 | Kernel ocupado rechecado/reservado durante o DELETE — review minor | `grep -n "has_busy_session\|reserve" backend/src/notisbook/api/catalog.py backend/src/notisbook/kernels/service.py` mostra a checagem imediatamente antes/ durante a exclusão | bugfix |
| T2 | DROP DATABASE que falha vira tombstone — review minor | `grep -n "tombstones.add" backend/src/notisbook/kernels/catalog_hook.py` inclui o ramo `except` de `drop_removed_db` | bugfix |
| T6 | Files recusa excluir pasta com aba de notebook aberta — review minor | `grep -n "isOpenUnder" frontend/src/components/data/FileTree.tsx` | bugfix |
| T5 | Front compila | `cd frontend && npm run typecheck` exit 0 | constraint |
| T5 | Menus e diálogos no Catalog | `grep -n "ContextMenu" frontend/src/components/data/CatalogSection.tsx`; `grep -n "showModal" frontend/src/components/shell/ConfirmDialog.tsx frontend/src/components/data/CreateSchemaDialog.tsx`; `grep -n "Create Schema\|Delete Schema" frontend/src/components/data/CatalogSection.tsx` | feature |
| T5 | Árvore visível com catálogo vazio | `grep -n "hasContent" frontend/src/components/data/CatalogSection.tsx` mostra a árvore renderizada sempre que há `data` | bugfix |
| T6 | Delete Folder no Files | `grep -n "Delete Folder" frontend/src/components/data/FileTree.tsx`; `grep -n "deleteDir" frontend/src/api/files.ts`; `npm run typecheck` exit 0 | feature |

## Arquivos previstos
- `backend/src/notisbook/catalog/managed.py` — T1
- `backend/src/notisbook/kernels/catalog_hook.py` — T1, T2
- `backend/src/notisbook/kernels/service.py` — T1, T3
- `backend/src/notisbook/catalog/registry.py` — T3
- `backend/src/notisbook/catalog/iceberg_jdbc.py` — T3
- `backend/src/notisbook/catalog/schemas.py` — T3
- `backend/src/notisbook/api/catalog.py` — T3
- `backend/src/notisbook/fs_safety.py` — T4
- `backend/src/notisbook/notebooks/store.py` — T4
- `backend/src/notisbook/api/contents.py` — T4
- `backend/src/notisbook/api/files.py` — T4
- `backend/src/notisbook/files/browser.py` — T4
- `frontend/src/components/shell/ConfirmDialog.tsx` — T5, T6
- `frontend/src/components/data/CreateSchemaDialog.tsx` — T5
- `frontend/src/components/data/CatalogSection.tsx` — T5
- `frontend/src/components/data/DataPanel.module.css` — T5, T6
- `frontend/src/api/catalog.ts` — T5
- `frontend/src/state/catalog.ts` — T5
- `frontend/src/components/data/FileTree.tsx` — T6
- `frontend/src/api/files.ts` — T6
- `frontend/src/state/files.ts` — T6
- `frontend/src/state/notebookTree.ts` — T6
- `.claude/plans/pendencias/TODO-menus-schema-e-pasta.md` — artefato de orquestração (nits do code review)

## Fora de escopo
- Menu em tabela, rename de schema, namespace Iceberg aninhado, tamanho da pasta na confirmação, migrar o `window.confirm` do painel Notebooks.
- Excluir `/tmp`, `/opt` e pastas ocultas pela UI (allowlist, D7).
- Cache do Iceberg em sessão aberta (tabela purgada pode falhar até reiniciar o kernel).
- Testes automatizados e extensão do roteiro de smoke (não autorizados, D10).
- **Documentação de produto** — nenhuma tocada. ADR do acoplamento ao formato interno do Iceberg só se o operador pedir.

## Não mexer
- `~/.notisbook` real: verificação só em `NOTISBOOK_HOME` isolado no scratchpad.
- Comportamento do DELETE do painel Notebooks (`/api/contents`).
- Sonda do painel Variables; célula SQL (`kernels/sql_cell.py`); `log4j2`.
- `global.css`; UI só em inglês; visual `.neo`.
- Leitura do catálogo (`GET /api/catalog`, `/columns`) e rótulo `spark`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | software-architect | OK | 486838 | 171038 |
| 1-2 | python-engineer | OK | 1051153 | 81805 |
| 3 | python-engineer | OK | 479015 | 101184 |
| 4 | python-engineer | OK | 166677 | 73001 |
| 5-6 | python-engineer | OK | 201661 | 89879 |
| 7 | code-review (skill) | ajustes necessários | 180231 | 108967 |
| 7 | plan-auditor | OK | 52840 | 30287 |
| 8 | python-engineer | OK | 503764 | 121237 |
| 9 | code-review (skill) | aprovar | 111289 | 113660 |
| 9 | plan-auditor | OK | 79421 | 37654 |
| 10 | plan-auditor | OK | 64989 | 44109 |
<!-- effort-ledger:end -->
