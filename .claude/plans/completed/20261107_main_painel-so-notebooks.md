# Painel só com notebooks e artefatos Spark em ~/.notisbook

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-07 01:05:50 -0300
Modificação: 2026-11-07 01:24:09 -0300
Finalização: 2026-11-07 01:24:09 -0300

## Objetivo

O painel Notebooks passa a mostrar só pastas e `.ipynb`, e o Spark deixa de criar `spark-warehouse/`, `metastore_db/` e `derby.log` na pasta do notebook (cwd do kernel): o warehouse padrão vai para `<raiz>/warehouse/spark` e o metastore Derby (com seu log) para `<raiz>/metastore`, onde `<raiz>` é `NOTISBOOK_HOME` ou `~/.notisbook`. Isso também unifica o catálogo entre notebooks de pastas diferentes. Pastas do usuário (ex.: `table2/`) continuam visíveis. Dados já existentes em `~/notebooks` são movidos/apagados à mão pelo operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Painel Notebooks exibe só `dir` e `notebook`; filtro no frontend, listagem completa preservada para `uniqueName` | python-engineer | — | 1 | escrita |
| T2 | `spark-defaults.conf` fixa warehouse padrão em `<raiz>/warehouse/spark` e Derby (`derby.system.home`) em `<raiz>/metastore`, também para versões sem bundle; `ensure_home` cria `<raiz>/metastore` | python-engineer | — | 1 | escrita |
| T3 | `revision` dos bundles sobe para que ambientes instalados apareçam como `outdated` | python-engineer | T2 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Filtro só no frontend | `uniqueName` (Untitled/New folder) continua vendo nomes escondidos e não gera 409 por colisão invisível; API `/api/contents` inalterada | `frontend/src/components/files/FileBrowser.tsx:176-188`, `frontend/src/state/workspace.ts:141-153`, `backend/src/notisbook/notebooks/store.py:176-177` | filtrar em `NotebookStore.list_dir` |
| D2 | Relocar artefatos Spark para a raiz de dados, não escondê-los por nome | segue a decisão de raiz única (`dados-do-notisbook-em-raiz-unica-notisbook-home`); unifica o catálogo entre pastas | `backend/src/notisbook/api/sessions.py:61-63` (cwd = pasta do notebook); `backend/src/notisbook/spark/bundles.py:150-168` não define warehouse/metastore | lista de nomes escondidos no painel |
| D3 | Ambientes existentes via bump de `revision` (outdated → reinstalar), sem regenerar `spark-defaults` no start | mecanismo previsto no módulo; regenerar no start sobrescreveria edições do usuário | `backend/src/notisbook/spark/bundles.py:4-6`, `backend/src/notisbook/spark/kernelspec.py:123` | reescrever `spark-defaults.conf` a cada start, como o log4j2 |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Entradas `file` não são renderizadas no painel | leitura de `frontend/src/components/files/FileBrowser.tsx`: a lista renderizada exclui `type === "file"`, e `uniqueName` continua recebendo a listagem completa | feature |
| T1 | Frontend compila | `cd frontend && npm run build` → exit 0 | constraint |
| T2 | `spark-defaults` com bundle fixa warehouse e Derby sob a raiz | `cd backend && uv run python -c "from pathlib import Path; from notisbook.spark.bundles import MATRIX, render_spark_defaults; c=render_spark_defaults(next(iter(MATRIX.values())), Path('/j'), Path('/h')); print('spark.sql.warehouse.dir /h/warehouse/spark' in c, '-Dderby.system.home=\"/h/metastore\"' in c)"` → `True True` | feature |
| T2 | Versão sem bundle também recebe warehouse e Derby | leitura de `backend/src/notisbook/spark/installer.py`: `spark-defaults.conf` é escrito mesmo sem bundle, com as duas linhas acima e sem `spark.jars`/extensões | feature |
| T2 | `ensure_home` cria `<raiz>/metastore` | `NOTISBOOK_HOME=<scratch>/m uv run python -c "from notisbook.config import Settings, ensure_home; s=Settings(); ensure_home(s); print((s.home/'metastore').is_dir())"` → `True` | feature |
| T2 | Nome `metastore` e subpasta `spark` vêm de constantes únicas | `git grep -n "\"metastore\"\|'metastore'" -- backend/src` → 1 ocorrência (definição) | refactor |
| T2 | Raiz com espaço no caminho não impede o driver de subir (valor de `extraJavaOptions` entre aspas) — achado minor do review, rodada 1 | Spark 3.5.9 instalado com `SPARK_CONF_DIR` gerado por `render_spark_defaults(None, ..., Path('<scratch>/a b'))`, `enableHiveSupport` + `saveAsTable` → sessão abre e `metastore_db`/`derby.log` aparecem em `<scratch>/a b/metastore` | bugfix |
| T3 | Todas as entradas de `MATRIX` com `revision` maior que a anterior (1 → 2) | `git grep -n "revision=" -- backend/src/notisbook/spark/bundles.py` → nenhuma `revision=1` | feature |

## Arquivos previstos
- `frontend/src/components/files/FileBrowser.tsx` — T1
- `backend/src/notisbook/spark/bundles.py` — T2, T3
- `backend/src/notisbook/spark/installer.py` — T2
- `backend/src/notisbook/config.py` — T2

## Fora de escopo
- Mover/apagar `~/notebooks/spark-warehouse`, `~/notebooks/metastore_db` e `~/notebooks/derby.log` — feito à mão pelo operador.
- Pastas do usuário com dados (ex.: `table2/`) — continuam visíveis.
- **Documentação de produto** — nenhuma.

## Não mexer
- API `/api/contents` e `NotebookStore.list_dir` (`backend/src/notisbook/notebooks/store.py`) (D1).
- Painel Data (`/api/fs/list`).
- cwd do kernel (`backend/src/notisbook/api/sessions.py`).
- Catálogo `iceberg` em `<raiz>/warehouse/iceberg`.

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 93181 | 55086 |
| 1 | python-engineer | OK | 41963 | 42055 |
| 1 | code-review | ajustes necessários | 57451 | 64832 |
| 1 | plan-auditor | CONFORME | 32377 | 26362 |
| 1 | python-engineer | OK | 32628 | 29629 |
| 1 | code-review | aprovar | 39694 | 58424 |
| 1 | plan-auditor | CONFORME | 35476 | 27466 |
<!-- effort-ledger:end -->
