# Painel Dados funcional (Files + Catalog)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-05 11:28:53 -0300
Modificação: 2026-11-05 13:12:48 -0300
Finalização: 2026-11-05 13:12:48 -0300

## Objetivo

Hoje o painel Dados (ícone 🗄️) é só visual. Ele passa a funcionar em duas seções:

- **Files** — o usuário escolhe qualquer diretório da máquina. O PATH absoluto aparece no topo, para usar no `spark.read`. A árvore segue o estilo IntelliJ, e o botão direito oferece "Copy Path", absoluto ou relativo à raiz escolhida.
- **Catalog** — mostra a árvore catálogo → banco → tabela → colunas, lida da SparkSession do kernel do notebook ativo.

**Escopo aceito pelo operador:** o catálogo vale só durante a sessão. Se o kernel reiniciar ou o notebook for reaberto, a lista some e volta quando o notebook roda de novo. A persistência entre kernels fica para um plano futuro. Tabelas que não aparecerem no Catalog, como Delta ou parquet gravados só por path, ficam acessíveis pelo Files.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | API de metadados de arquivos (`/api/fs/places`, `/api/fs/list`) + checagem de Host nas rotas novas | python-engineer | — | 1 | escrita |
| T2 | Introspecção silenciosa do catálogo no kernel + `GET /api/sessions/{id}/catalog` e `/catalog/columns` | python-engineer | — | 2 | escrita |
| T3 | Files no frontend: seletor de diretório, PATH no topo, árvore ARIA lazy, ícones por tipo | python-engineer | T1 | 3 | escrita |
| T4 | Menu de contexto + Copy Path absoluto / relativo à raiz escolhida | python-engineer | T3 | 4 | escrita |
| T5 | Árvore do Catalog a partir da sessão do notebook ativo | python-engineer | T2 | 5 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3
- Wave 4 (serial, escrita): T4
- Wave 5 (serial, escrita): T5

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | ~~Seletor servido pelo backend~~ → **revisada após teste do operador (commit 5e69c25): "Alterar diretório" abre o "Escolher pasta" nativo do macOS via backend (`osascript choose folder`); fallback = campo de colar caminho absoluto; atalhos e navegação in-app saem** | O seletor in-app ficou ruim no uso real; o diálogo do navegador não entrega caminho absoluto, e o `spark.read` precisa dele | teste do operador em 2026-11-05 sobre `5e69c25` | Manter o seletor in-app redesenhado; `showDirectoryPicker` do navegador (sem caminho absoluto). Custos aceitos pelo operador: só macOS, janela pode abrir atrás do navegador, prompt de permissão, sem teste por curl |
| D2 | API nova sem estado, só leitura de metadados, independente do `NotebookStore`. Exige token + Host confiável, não usa `resolve()`, pagina, carrega por nó e não segue symlinks | O token já permite executar código arbitrário no kernel, então listar nomes fora da raiz não dá poder novo. A defesa fica em "só o app chega na API" e "nunca ler conteúdo" | `backend/src/notisbook/notebooks/store.py:88-103`; `backend/src/notisbook/security.py:44-65` (Host/Origin só no WS) | Estender o `NotebookStore` para fora da raiz; guardar a raiz no servidor (cria estado e endpoint de escrita sem ganho) |
| D3 | Catálogo lido da SparkSession viva do kernel ativo, por `execute` silencioso (`user_expressions`) desviado no `_shell_loop`, fora do WS. Usa `getActiveSession()` e nunca `getOrCreate`. Responde com cache e `stale` quando o kernel está ocupado | Mostra fielmente as tabelas managed, external, views e temp views, com custo baixo e reversível | `backend/src/notisbook/kernels/service.py:195-201,245-253` (msg_id fora de `pending` é descartado) | Metastore Derby embarcado compartilhado (aceita só um processo); Derby em modo servidor ou Hive metastore (sem `derbynet` no wheel pyspark 4.1.3, exige processo Java); varrer o warehouse (perde external e colunas). Persistência adiada por decisão do operador |
| D4 | O Copy Path relativo é calculado a partir do diretório escolhido no Files (a raiz vira `.`). A raiz fica em `localStorage` | Equivale ao "Path From Content Root" do IntelliJ. O `DataPanel` não está ligado a um notebook | `frontend/src/components/shell/AppShell.tsx:31-35` (fora do `NotebookProvider`) | Relativo à pasta do notebook (cwd do kernel): varia por aba e gera `../..` |
| D5 | `python-engineer` implementa também o frontend React/TS | O harness não tem agente de React; foi assim no MVP | `sem evidência — aceite do operador` | — |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Lista diretório absoluto fora da raiz | `curl -s -H "Authorization: Bearer $T" "http://127.0.0.1:$P/api/fs/list?path=$HOME" \| jq '.path,(.entries\|length),.truncated'` → `"$HOME"`, número > 0, `false` | feature |
| T1 | Rejeita caminho relativo, sem token e Host estranho | mesmo endpoint: `?path=foo` → 400; sem header → 401; `-H "Host: evil.test:$P"` → 403 (`curl -o /dev/null -w '%{http_code}'`) | constraint |
| T1 | Paginação | `?path=/usr/bin&limit=50` → `jq '.truncated,.next_offset'` = `true`, `50` | feature |
| T1 | Symlink marcado e não seguido | `?path=/` → `jq '.entries[]\|select(.name=="tmp")\|.is_symlink,.path'` = `true`, `"/tmp"` | feature |
| T1 | Atalhos | `curl …/api/fs/places \| jq 'map(.label)'` contém `"Home"` e `"Notebooks"` | feature |
| T1 | Módulo não lê conteúdo de arquivo | `grep -rnE "open\(\|read_text\|read_bytes" backend/src/notisbook/files/` → vazio | constraint |
| T2 | Execução interna é silenciosa | `grep -n "silent=True" backend/src/notisbook/kernels/service.py` → ≥ 1 linha | feature |
| T2 | Sem SparkSession: não cria uma | kernel sem Spark iniciado: `curl …/api/sessions/$SID/catalog \| jq -r .status` → `no_spark_session` e `pgrep -f SparkSubmit` sem processo novo | constraint |
| T2 | Lista managed e external com Hive habilitado | após células `SparkSession.builder.enableHiveSupport().getOrCreate()`, `CREATE TABLE t1 USING parquet AS SELECT 1 a` e `CREATE TABLE ext (a INT) USING parquet LOCATION '/tmp/nb_ext'`: `jq '[.catalogs[].databases[].tables[]\|{name,table_type}]'` contém t1 `MANAGED` e ext `EXTERNAL` | feature |
| T2 | Colunas sob demanda | `curl …/catalog/columns?database=default&table=t1 \| jq -r '.[0].name'` → `a` | feature |
| T2 | Não polui o kernel do usuário | a célula seguinte tem `execution_count` consecutivo e `dir()` antes/depois da consulta tem o mesmo conjunto | constraint |
| T2 | Kernel ocupado não bloqueia | durante `time.sleep(20)` numa célula, `/catalog` responde em < 2 s com `jq .stale` = `true` | feature |
| T3 | Frontend compila | `npm --prefix frontend run typecheck && npm --prefix frontend run build` → exit 0 | constraint |
| T3 | Placeholder removido, testids preservados | `grep -n "Em breve" frontend/src/components/data/DataPanel.tsx` → vazio; `grep -nE 'data-files\|files-select-dir' frontend/src/components/data/` → ≥ 2 linhas | feature |
| T3 | Árvore ARIA | `grep -rnE 'role="treeitem"\|aria-expanded' frontend/src/components/data/` → ≥ 2 linhas | feature |
| T3 | Raiz persistida | `grep -rn "localStorage" frontend/src/` com chave da raiz do Files → ≥ 1 linha | feature |
| T4 | Copy Path absoluto e relativo | `grep -rn "navigator.clipboard" frontend/src/` → ≥ 1 linha; `grep -rnE "onContextMenu" frontend/src/components/` → ≥ 1 linha; typecheck + build exit 0 | feature |
| T5 | Catalog consome a API da sessão ativa | `grep -rn "/catalog" frontend/src/api/` → ≥ 1 linha; `grep -n 'data-catalog' frontend/src/components/data/DataPanel.tsx` → ≥ 1 linha; typecheck + build exit 0 | feature |
| R1 | Probe do catálogo não empilha nem varre sem limite (review major) | `grep -n "_probe_tasks" backend/src/notisbook/kernels/service.py` mostra retorno do cache quando há probe em voo; `grep -nE "MAX_TABLES\|limit" backend/src/notisbook/kernels/introspect.py` → ≥ 1 linha | bugfix |
| R1 | Refresh automático em `idle` com debounce (review major) | `grep -nE "debounce\|setTimeout" frontend/src/components/data/CatalogSection.tsx` → ≥ 1 linha; typecheck + build exit 0 | bugfix |
| R2 | Colunas de temp view e global temp view resolvem (review major) | após `spark.range(1).createOrReplaceTempView("v")` e `createOrReplaceGlobalTempView("g")`: `/catalog/columns?table=v` e `?database=global_temp&table=g` → `jq -r '.[0].name'` = `id` | bugfix |
| R3 | Colunas não ficam em "Carregando…" após refresh (review minor) | `frontend/src/state/catalog.ts`: resposta descartada por geração zera `loading` ou `expand` recarrega entrada de geração antiga (leitura do código) | bugfix |
| R4 | Chave de cache de colunas sem ambiguidade (review minor) | `grep -n "json.dumps" backend/src/notisbook/api/catalog.py` → ≥ 1 linha | bugfix |
| R5 | Cache da sessão limitado (review minor) | `grep -nE "OrderedDict\|MAX_CACHE" backend/src/notisbook/kernels/service.py` → ≥ 1 linha | bugfix |
| R6 | `stat` só no recorte paginado (review minor) | `/api/fs/list?path=/usr/bin&limit=50` mantém `truncated`=`true`, `next_offset`=`50`; `_entry`/`stat` chamado após o slice em `browser.py` | bugfix |
| R7 | ~~"Carregar mais" do seletor não vaza para outra pasta (review minor) ~~ **superado por R19 (D1 revisada: seletor in-app removido)** | `grep -nE "AbortController\|res.path === " frontend/src/components/data/DirectoryPicker.tsx` → ≥ 1 linha | bugfix |
| R8 | Marcador `data-catalog` real no DataPanel (auditoria) | `grep -n 'data-catalog' frontend/src/components/data/DataPanel.tsx` mostra atributo JSX, não comentário | feature |
| R9 | Varredura para no limite de verdade (review r2 major) | `introspect.py`: após `max_total`, bancos restantes saem `truncated` sem chamada de listagem; listagem por banco interrompida no limite sem materializar a lista inteira, mantendo `table_type` (leitura do código + `/catalog` ainda traz `table_type`) | bugfix |
| R10 | Releitura automática quando `busy`/`stale` com kernel em idle (review r2 major) | `grep -nE "backoff\|retry" frontend/src/state/catalog.ts frontend/src/components/data/CatalogSection.tsx` → ≥ 1 linha; typecheck + build exit 0 | bugfix |
| R11 | Colunas relidas após o catálogo e 409 `busy` com nova tentativa (review r2 minor) | `frontend/src/state/catalog.ts`: colunas expandidas recarregadas depois de `getCatalog` resolver; `loadColumns` trata 409 com nova tentativa (leitura do código) | bugfix |
| R12 | Falha de um banco não derruba o probe; temp views locais sobrevivem ao limite (review r2 minor) | `introspect.py`: `try/except` por banco em torno da listagem; limite não usa `break` que descarta temporárias (leitura do código) | bugfix |
| R13 | ~~"Usar esta pasta" não seleciona a pasta anterior (review r2 minor) ~~ **superado por R19 (D1 revisada: botão "Usar esta pasta" e navegação removidos)** | `DirectoryPicker.tsx`: botão desabilitado com `loading \|\| error` ou `listing` limpo na troca (leitura do código) | bugfix |
| R14 | Banco com falha aparece como falha, não como vazio (review r3 minor) | `grep -nE "error\?: string\|truncated\?: boolean" frontend/src/api/catalog.ts` → ≥ 2 linhas; `CatalogSection.tsx` mostra linha de falha quando `d.error` (leitura do código); typecheck + build exit 0 | bugfix |
| R15 | Temp views locais puladas sem montar o dict em `_scan` (review r3 minor) | `introspect.py`: `isTemporary()` lido antes de `_jtable`; temp local (namespace vazio) pulada sem chamadas extras (leitura do código) | bugfix |
| R16 | Sem ramo morto nem comentário desatualizado em `_catalogs` (review r4 minor) | `grep -n "Local temp views show up under every database" backend/src/notisbook/kernels/introspect.py` → vazio; `grep -n "temps.setdefault" backend/src/notisbook/kernels/introspect.py` → vazio | refactor |
| R17 | Files e Catalog com rolagem própria, painel sem rolagem infinita (teste do operador, commit 5e69c25) | `grep -nE "overflow(-y)?: *auto" frontend/src/components/data/DataPanel.module.css` → ≥ 2 linhas; typecheck + build exit 0; no app: com uma pasta grande expandida, só a área de Files rola e o Catalog continua visível | bugfix |
| R18 | Endpoint do diálogo nativo seguro | `grep -rn "choose folder" backend/src/notisbook/files/` → ≥ 1 linha; `grep -rnE "shell=True\|os.system" backend/src/notisbook/files/ backend/src/notisbook/api/files.py` → vazio; `curl -X POST …/api/fs/choose-dir` sem token → 401 e com `Host: evil.test` → 403 | constraint |
| R18 | Diálogo abre e devolve caminho absoluto | no app (macOS): "Alterar diretório" abre o Finder na frente; escolher uma pasta põe o caminho absoluto no topo do Files; cancelar mantém a raiz atual | feature |
| R19 | Seletor in-app substituído, campo de colar mantido | `grep -n "getPlaces" frontend/src/components/data/DirectoryPicker.tsx frontend/src/components/data/FilesSection.tsx` → vazio; campo de caminho absoluto ainda presente (leitura do código); typecheck + build exit 0 | feature |
| R20 | Mensagens distintas para 409/504 do Finder (review r6 minor) | `FilesSection.tsx`: 409 → aviso de seletor já aberto sem abrir o campo manual; 504 → tempo esgotado; demais erros usam o `detail` do backend (leitura do código); typecheck + build exit 0 | bugfix |
| R21 | Árvore nunca colapsa para 0 px em painel baixo (review r6 minor) | `grep -nE "min-height: *[0-9]+px" frontend/src/components/data/DataPanel.module.css` mostra altura mínima útil em `.tree` ou `.section` comportando controles + árvore (leitura do código) | bugfix |
| R22 | Catalog sem o nome do notebook no topo (teste do operador, commit 02509b9) | `CatalogSection.tsx` não renderiza o nome/caminho do notebook ativo no cabeçalho; botão de atualizar continua no cabeçalho (leitura do código); typecheck + build exit 0 | bugfix |

## Arquivos previstos
- `backend/src/notisbook/files/__init__.py` — T1
- `backend/src/notisbook/files/browser.py` — T1
- `backend/src/notisbook/api/files.py` — T1, R18
- `backend/src/notisbook/files/native_picker.py` — R18
- `backend/src/notisbook/security.py` — T1
- `backend/src/notisbook/app.py` — T1, T2
- `backend/src/notisbook/kernels/introspect.py` — T2
- `backend/src/notisbook/kernels/service.py` — T2
- `backend/src/notisbook/api/catalog.py` — T2
- `frontend/src/api/files.ts` — T3, R19
- `frontend/src/state/files.ts` — T3
- `frontend/src/components/data/DataPanel.tsx` — T3, T5
- `frontend/src/components/data/FilesSection.tsx` — T3
- `frontend/src/components/data/FileTree.tsx` — T3, T4
- `frontend/src/components/data/DirectoryPicker.tsx` — T3
- `frontend/src/components/shell/icons.tsx` — T3
- `frontend/src/styles` (CSS do painel) — T3, T4, T5
- `frontend/src/components/shell/ContextMenu.tsx` — T4
- `frontend/src/api/catalog.ts` — T5, R14
- `frontend/src/components/data/CatalogSection.tsx` — T5, R1, R2, R8
- `frontend/src/components/data/DataPanel.module.css` — T3, T4, T5 (CSS do painel; ampliação registrada: o CSS já morava aqui, não em `frontend/src/styles`)
- `frontend/src/state/catalog.ts` — T5, R3 (ampliação registrada: store do Catalog)

## Fora de escopo
- Preview ou leitura de conteúdo de arquivo e operações de arquivo (criar, renomear, apagar): não pedidos.
- Metastore/warehouse persistente e compartilhado entre kernels: adiado pelo operador para um plano futuro.
- Listagem a fundo de catálogos v2 (Iceberg/Delta) e detecção de tabelas Delta só por path: amadurecer depois; o acesso fica pelo Files.
- Watcher de filesystem e atualização da árvore em tempo real: o refresh é manual ou ao expandir.
- Caminho relativo ao notebook: descartado em D4.
- Checagem de Host nos routers existentes: follow-up.
- Testes automatizados persistidos: não pedidos.
- **Documentação de produto** — nenhuma. Não há README ou ARCHITECTURE descrevendo o painel Dados; se surgir, é reportada ao operador no fim.

## Não mexer
- `backend/src/notisbook/notebooks/store.py` (`_clean`/`resolve`/`list_dir`): o confinamento à raiz de notebooks fica intacto.
- `backend/src/notisbook/kernels/protocol.py` e o tráfego do WS de célula.
- A fila serial de execução de células no frontend (`frontend/src/state/kernel.ts`).
- `backend/src/notisbook/spark/kernelspec.py` (env/`JAVA_HOME`).
- A semântica de `require_token` em `security.py`.
- A ausência de `jupyter_server` e a posição do `DataPanel` no `AppShell`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  — concluído e validado pelo operador (commits 5e69c25, 02509b9, 0df9e58); R1–R22 aplicados, R7/R13 superados por R19

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 101460 | 83839 |
| 0 | software-architect | OK | 260527 | 58213 |
| 1 | python-engineer | OK | 176691 | 42704 |
| 2 | python-engineer | OK | 225017 | 76270 |
| 3 | python-engineer | OK | 115045 | 60450 |
| 4 | python-engineer | OK | 48819 | 43492 |
| 5 | python-engineer | OK | 112107 | 68397 |
| review | plan-auditor | OK | 55024 | 34656 |
| review | code-review | OK | 130525 | 100179 |
| loop-1 | python-engineer | OK | 141848 | 65822 |
| review-2 | plan-auditor | OK | 42230 | 34728 |
| review-2 | code-review | OK | 210646 | 107853 |
| loop-2 | python-engineer | OK | 136353 | 60920 |
| review-3 | plan-auditor | OK | 58977 | 38818 |
| review-3 | code-review | OK | 166147 | 114097 |
| loop-3 | python-engineer | OK | 60347 | 39617 |
| review-4 | plan-auditor | OK | 71127 | 41702 |
| review-4 | code-review | OK | 90859 | 99059 |
| loop-4 | python-engineer | OK | 50500 | 33107 |
| review-5 | code-review | OK | 47805 | 92233 |
| review-5 | plan-auditor | OK | 50226 | 42127 |
| loop-5 | python-engineer | OK | 39179 | 38312 |
| loop-6 | python-engineer | OK | 67799 | 44234 |
| review-6 | plan-auditor | OK | 81526 | 44663 |
| review-6 | code-review | OK | 99357 | 76655 |
| loop-7 | python-engineer | OK | 18906 | 31126 |
| review-7 | code-review | OK | 81697 | 106167 |
| review-7 | plan-auditor | OK | 69830 | 50374 |
| loop-8 | python-engineer | OK | 17810 | 34573 |
| review-8 | code-review | OK | 33300 | 60679 |
| review-8 | plan-auditor | OK | 59564 | 33868 |
| review-9 | plan-auditor | OK | 74086 | 39378 |
<!-- effort-ledger:end -->
