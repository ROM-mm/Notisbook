# Notisbook — MVP FastAPI + React

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-05 02:40:09 -0300
Modificação: 2026-11-05 10:54:51 -0300
Finalização: 2026-11-05 10:54:51 -0300

## Objetivo

App local (macOS, usuário único) que substitui o Jupyter Notebook por uma UI própria em React, com gestão de versões do Apache Spark pela interface. Notebooks seguem `.ipynb` (nbformat v4). `install-spark.sh` e `start-jupyter.sh` são aposentados após paridade. Abordagem: um processo FastAPI em `127.0.0.1` com token, kernels via `jupyter_client` (`AsyncKernelManager` atrás de `KernelService`) e WebSocket v1 orientado a célula — escolhido sobre `jupyter_server` embutido para dar protocolo simples à UI e controle do env do kernel. Frontend F1–F4 delegado ao agente `general-purpose` com `write_scope: frontend/**` (aceite do operador: não há engineer de React no harness). Ampliação de escopo aprovada em 2026-11-05 09:08:25 -0300: visual passa ao padrão Databricks (D10, substitui D7) — barra superior com menus e Settings, barra lateral com 2 ícones (Dados, Notebooks), abas de notebooks, células numeradas com título; gestão do Spark vive em Settings.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Esqueleto backend: app, config, CLI, token/cookie, bind local, guarda Origin/Host no WS, lifespan | python-engineer | — | 1 | escrita |
| T2 | Contents: listar/ler/salvar/criar/renomear `.ipynb`, caminho seguro, gravação atômica | python-engineer | T1 | 2 | escrita |
| T3 | Kernelspecs, sessões e canal WS v1 (execute/interrupt/restart, roteamento iopub, shutdown) | python-engineer | T1 | 3 | escrita |
| T4 | Gestor Spark: prereqs, catálogo, instalador com diretório versionado, kernelspec com env, jobs por WS, remoção | python-engineer | T1,T3 | 4 | escrita |
| T7 | Catálogo dinâmico: versões estáveis do pyspark no PyPI dos últimos 6 meses, com fallback offline | python-engineer | T4 | 5 | escrita |
| T8 | JDK por versão do Spark: 3.x → JDK 17 exato; 4.x → JDK 21 se houver, senão 17; prereqs por linha | python-engineer | T7 | 6 | escrita |
| F1 | Frontend: Vite+React+TS strict, cliente API/WS, file browser, shell | general-purpose | T1,T2 | 7 | escrita |
| F2 | Editor de notebook: células code/markdown com CodeMirror 6, atalhos, salvar | general-purpose | F1 | 8 | escrita |
| F3 | Renderizadores de saída (DOMPurify + Shadow DOM, ANSI) e controles do kernel | general-purpose | F2,T3 | 9 | escrita |
| F4 | Tela Settings com gestão do Spark (combobox do catálogo, remover, prereqs/JDKs) e seletor de ambiente na barra superior | general-purpose | F5,T4,T7,T8 | 12 | escrita |
| F5 | Visual Databricks: barra superior (título, seletor, Run all, menus File/Edit/View/Run/Help/Settings), barra lateral com 2 ícones (Dados, Notebooks), abas de notebooks, células com número/título/menu ⋮ e código em JetBrains Mono, painel Dados só visual (Catalog, Files) | general-purpose | F3 | 10 | escrita |
| T9 | Correções pós-review (backend): guarda `starting` em execute, `_await_ready` com except genérico, accept+close 4404 em sessão/job inexistente, limpeza de comentários | python-engineer | T3,T4 | 14 | escrita |
| F6 | Correções pós-review (frontend): reconexão com célula em execução aborta e segue a fila, `not_found` tratado, limpeza de comentários | general-purpose | T9 | 15 | escrita |
| T5 | Servir `frontend/dist` com fallback SPA + CSP; `start.sh` de um comando que abre o navegador autenticado | python-engineer | T1,F1 | 11 | escrita |
| T6 | Remover `install-spark.sh`, `start-jupyter.sh` e `pyproject.toml` da raiz | python-engineer | T4,T5 | 13 | escrita |

## Ordem de execução (waves)
- Waves 1–15 (serial, escrita): T1 → T2 → T3 → T4 → T7 → T8 → F1 → F2 → F3 → F5 → T5 → F4 → T6 → T9 → F6

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Frontend React + Vite, servido pelo FastAPI, aberto no navegador | mais leve na prática; saídas Jupyter são HTML/JS | sem evidência — preferência do operador | Swift nativo (WebView de qualquer forma, editor inexistente); Electron (peso); Tauri adiado p/ fase 3 |
| D2 | `jupyter_client` direto + protocolo WS v1 por célula | UI simples e controle do env do kernel | parecer do software-architect | `jupyter_server` embutido (Tornado ao lado do FastAPI, front preso ao protocolo do Lab) — plano de fuga atrás da `KernelService` |
| D3 | Instalação Spark em diretório versionado `envs/spark-<v>-<id>/` + troca do kernelspec | uma instalação só, rollback trivial | `install-spark.sh:105-142` instala duas vezes | staging + reinstalação (atual) |
| D4 | Kernelspec com `env` explícito (JAVA_HOME, PYSPARK_PYTHON/DRIVER) sem SPARK_HOME/PYTHONPATH | kernel determinístico | `install-spark.sh:154`; limpeza só em `start-jupyter.sh:9-12` | só `unset` no launcher |
| D5 | HTML de saída via DOMPurify + Shadow DOM | altura automática sem JS | sem evidência — parecer do architect | iframe sandbox (adiado com suporte a JS) |
| D6 | Frontend F1–F4 pelo agente `general-purpose` com `write_scope: frontend/**` | harness sem engineer de React | sem evidência — aceite do operador | criar `frontend-engineer` antes; python-engineer (fora do contrato) |
| D7 | (SUCEDIDA por D10) Referência visual: estética Deepnote (espaço em branco, tipografia, blocos limpos, toolbar da célula no hover, tema claro/escuro) + do Databricks só o seletor de ambiente no header e o rodapé de execução por célula; inspiração, sem copiar logos/assets | UI elegante sem a densidade corporativa do Databricks; elementos do Databricks úteis p/ Spark | sem evidência — preferência do operador | Databricks integral (denso); Jupyter clássico |
| D8 | Versões do Spark escolhidas em combobox alimentado pelo PyPI (lançamentos estáveis dos últimos 180 dias), não digitadas | evita digitação errada e mostra só o que existe | sem evidência — preferência do operador | campo de texto livre; lista fixa 3.5.9/4.3.0 |
| D9 | JAVA_HOME do kernelspec escolhido pela linha do Spark: 3.x → JDK 17; 4.x → JDK 21, senão 17 | `java_home -v 17+` pega o JDK mais novo (Temurin 25 na máquina), sem suporte oficial no Spark 3.5 | retorno T4 (descoberta 3) | `-v 17+` genérico; JDK fixo único |
| D10 | Visual padrão Databricks (substitui D7): barra superior sem Connect/Schedule/Share, menus + Settings, barra lateral com 2 ícones (Dados, Notebooks), abas, células numeradas com título e menu ⋮ | operador considera o visual do Databricks o melhor | print do Databricks enviado pelo operador | estética Deepnote (D7) |
| D11 | Gestão do Spark e seletor de ambiente: gestão em Settings; seletor no lugar do seletor de linguagem da barra superior | só 2 ícones na barra lateral | sem evidência — preferência do operador | item próprio na barra lateral; botão Connect |
| D12 | Título da célula gravado em `metadata.title` da célula no `.ipynb` | simples e compatível com Jupyter/VS Code | sem evidência — aceite do operador | formato de exportação do Databricks |
| D13 | Painel Dados nesta etapa é só visual (Catalog em cima, Files embaixo com botão de selecionar diretório e árvore) | operador quer o visual primeiro e programar os eventos depois | sem evidência — preferência do operador | implementar Catalog/Files agora |
| D14 | Fonte de código das células (editor e saídas em texto): JetBrains Mono, empacotada localmente no bundle (pacote npm `@fontsource/jetbrains-mono`, licença OFL), com fallback monospace | preferência do operador; CSP `default-src 'self'` proíbe fonte de CDN | sem evidência — preferência do operador | fonte do sistema; Google Fonts via CDN |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Sem token → 401; com token → 200 | `curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8765/api/health` → `401`; com `-H "Authorization: Bearer $T"` → `200` e corpo `{"status":"ok"}` | feature |
| T1 | Bind só local | `lsof -nP -iTCP:8765 -sTCP:LISTEN` mostra apenas `127.0.0.1:8765` | constraint |
| T1 | Sem bind aberto nem shell | `grep -rnE "0\.0\.0\.0\|shell=True" backend/src` → vazio | constraint |
| T1 | WS rejeita Origin estranho | handshake WS com `Origin: http://evil.test` → status ≠ 101 | feature |
| T2 | Path traversal bloqueado | `curl -H "Authorization: Bearer $T" '127.0.0.1:8765/api/contents/%2e%2e%2f%2e%2e%2fetc%2fpasswd'` → 400 ou 404; symlink p/ `/etc` na raiz → 403 | feature |
| T2 | Notebook inválido recusado; só `.ipynb` gravável | `PUT` JSON não-nbformat → 422; `PUT x.txt` → 400 | feature |
| T2 | Arquivo criado é nbformat válido | `uv run --project backend python -c "import nbformat,sys;nbformat.validate(nbformat.read(sys.argv[1],as_version=4))" <arquivo>` → exit 0 | feature |
| T3 | Execução devolve saída | WS `execute` `print(1+1)` → `output` stream stdout `"2\n"` + `execute_reply` `ok` | feature |
| T3 | Interrupt | `time.sleep(60)` + `interrupt` → `error` `ename=="KeyboardInterrupt"` em ≤ 5 s | feature |
| T3 | Restart limpa estado | `x=1`, `restart`, `x` → `ename=="NameError"`; status `restarting` e `idle` emitidos | feature |
| T3 | Sem kernel órfão | `pgrep -f ipykernel_launcher \| wc -l` → `0` em ≤ 5 s após SIGTERM no servidor | constraint |
| T3 | Kernel inexistente | `POST /api/sessions` com `kernel_name` inexistente → 404 | feature |
| T4 | Prereqs | `GET /api/system/prereqs` → JSON com `uv.found`, `java.version`, `java.ok` booleano | feature |
| T4 | Versão validada | `POST /api/spark/versions {"version":"3.5.9; rm -rf /"}` → 422 | constraint |
| T4 | Instalação + kernelspec | `POST {"version":"3.5.9"}` → 202 e job `succeeded`; `jq '.env.PYSPARK_PYTHON,.argv[0]' ~/Library/Jupyter/kernels/spark359/kernel.json` → caminhos sob `$SPARK_LABS_HOME`; python do kernelspec `-c 'import pyspark;print(pyspark.__version__)'` → `3.5.9` | feature |
| T4 | Falha atômica | `POST {"version":"9.9.9"}` → job `failed`; kernelspec anterior intacto; `ls -d $SPARK_LABS_HOME/envs/spark-9.9.9-* 2>/dev/null \| wc -l` → `0` | feature |
| T4 | Concorrência | 2º POST da mesma versão em andamento → 409 | feature |
| T4 | Spark executa via canal T3 | `SparkSession.builder.master("local[1]").getOrCreate().range(3).count()` → stdout `3\n` | feature |
| T7 | Catálogo dos últimos 6 meses | `GET /api/spark/catalog` → 200, lista `[{version, released_at, installed}]`; todo `version` casa `^[0-9]+\.[0-9]+\.[0-9]+$` (sem rc/dev/preview) e todo `released_at` ≥ hoje − 180 dias, salvo `fallback: true` | feature |
| T7 | Janela vazia não deixa combobox vazio | com janela sem lançamentos, resposta traz as 3 estáveis mais recentes e `fallback: true` | feature |
| T7 | PyPI fora do ar | com `https://pypi.org` inacessível (ex.: `NOTISBOOK_PYPI_URL=http://127.0.0.1:9` no processo), `GET /api/spark/catalog` → 200 com `source: "fallback"` e lista não vazia | feature |
| T7 | Instaladas marcadas | versão instalada aparece com `installed: true` | feature |
| T8 | Spark 3.x usa JDK 17 | após instalar 3.5.9 (diretórios temporários), `jq -r .env.JAVA_HOME $JUPYTER_DATA_DIR/kernels/spark359/kernel.json` = saída de `/usr/libexec/java_home -v 17` | feature |
| T8 | Spark 4.x usa JDK 21, senão 17 | após instalar uma 4.x, `jq -r .env.JAVA_HOME` do kernel.json = `/usr/libexec/java_home -v 21` se existir, senão `-v 17` | feature |
| T8 | Prereqs por linha do Spark | `GET /api/system/prereqs` traz `java.jdks` (lista `{version, home}`) e `java.spark3_ok`/`java.spark4_ok` booleanos | feature |
| T8 | JDK ausente falha antes de instalar | instalação cuja linha não tem JDK compatível → job `failed` com `error` contendo `JDK` e nenhum diretório novo em `envs/` | feature |
| F1 | Build e tipos | `npm --prefix frontend run build` → exit 0 e `frontend/dist/index.html` existe; `npx --prefix frontend tsc --noEmit -p frontend` → exit 0 | feature |
| F1 | Tokens de design com tema claro e escuro | `test -f frontend/src/styles/tokens.css` → exit 0; `grep -cE -- '--color-' frontend/src/styles/tokens.css` ≥ 1; `grep -nE 'prefers-color-scheme: dark\|data-theme="dark"' frontend/src/styles/tokens.css` encontra | feature |
| F1 | TS strict e proxy WS | `grep -n '"strict": true' frontend/tsconfig.json` encontra; `grep -n "ws: true" frontend/vite.config.ts` encontra | constraint |
| F2 | Editor CodeMirror | `grep -rn "@codemirror/lang-python" frontend/src` encontra; build passa | feature |
| F2 | Salvar pela UI gera `.ipynb` válido com kernelspec | `nbformat.validate` (comando de T2) → exit 0; `jq .metadata.kernelspec.name <arquivo>` → `"spark359"` | feature |
| F3 | HTML sempre sanitizado | `grep -rln "dangerouslySetInnerHTML" frontend/src` → só `components/outputs/*`, cada um com `DOMPurify.sanitize` (`grep -n`) | constraint |
| F3 | Sem eval | `grep -rnE "\beval\(\|new Function\(" frontend/src` → vazio | constraint |
| F3 | XSS neutralizado | executar `HTML('<img src=x onerror=alert(1)><table><tr><td>ok</td></tr></table>')`; no console `document.querySelectorAll('[onerror]').length` (incl. shadow roots) → `0` | feature |
| F3 | Rodapé com tempo de execução por célula | executar `import time; time.sleep(1)`; no console `document.querySelector('[data-testid="cell-duration"]').textContent` casa `^[0-9]+(\.[0-9]+)? ?s$` com valor ≥ 1 | feature |
| F4 | Seletor de ambiente na barra superior | no console `document.querySelector('[data-testid="notebook-topbar"] [data-testid="kernel-selector"]')` → não-nulo | feature |
| F4 | Gestão do Spark em Settings | clicar `[data-testid="menu-settings"]` exibe `[data-testid="spark-version-select"]` | feature |
| F4 | Instalação pela UI com log ao vivo | aba Network mostra WS `/api/jobs/<id>/events` com > 1 mensagem; `GET /api/spark/versions` lista a versão | feature |
| F4 | Remover bloqueado com sessão ativa | `DELETE /api/spark/versions/<v>` com sessão aberta → 409 | feature |
| F4 | Versão escolhida em combobox do catálogo | as `option` de `[data-testid="spark-version-select"]` = `version` de `GET /api/spark/catalog`; não existe `input[type=text]` de versão em `components/spark` (`grep -rn 'spark-version-input' frontend/src` → vazio); escolher uma opção e instalar dispara `POST /api/spark/versions` com essa versão (aba Network) | feature |
| F4 | N versões coexistem | após instalar 2 versões, `document.querySelectorAll('[data-testid="spark-version-row"]').length` ≥ 2 e `GET /api/kernelspecs` lista os 2 kernels | feature |
| F4 | Remover versão pela UI | botão `[data-testid="spark-version-remove"]` sem sessão ativa dispara `DELETE /api/spark/versions/<v>` → 2xx e a linha some; `GET /api/spark/versions` não a lista | feature |
| F5 | Barra lateral com 2 ícones | `document.querySelectorAll('[data-testid="sidebar-nav"] [data-testid^="nav-"]').length` → `2` (`nav-data`, `nav-notebooks`) | feature |
| F5 | Sem Connect/Schedule/Share | `grep -rniE '>\s*(Connect|Schedule|Share)\s*<' frontend/src` → vazio | constraint |
| F5 | Menus na barra superior | `[data-testid="notebook-topbar"]` contém `menu-file`, `menu-edit`, `menu-view`, `menu-run`, `menu-help`, `menu-settings` e `run-all` (querySelector não-nulo para cada) | feature |
| F5 | Abas de notebooks | abrir 2 notebooks → `document.querySelectorAll('[data-testid="notebook-tab"]').length` = 2; clicar na 1ª aba muda o título exibido em `[data-testid="notebook-title"]` | feature |
| F5 | Célula numerada com título persistido | `[data-testid="cell-number"]` da 1ª célula = `1`; editar título e salvar → `jq '.cells[0].metadata.title' <arquivo>` = título digitado | feature |
| F5 | Painel Dados só visual | clicar `nav-data` exibe `[data-testid="data-catalog"]` e `[data-testid="data-files"]` (este com botão `[data-testid="files-select-dir"]`) | feature |
| T5 | CSP e fallback SPA | `curl -sI 127.0.0.1:8765/` contém `content-security-policy:` e `script-src 'self'`; `curl -s .../notebooks/qualquer` com cookie → HTML do `index.html` | feature |
| T5 | start.sh | `bash start.sh --no-browser` imprime URL casando `http://127.0.0.1:[0-9]+/\?token=`; `head -1 start.sh` → `#!/usr/bin/env bash` | feature |
| T5 | Abertura autônoma em um comando | `./start.sh` sem argumentos (com `frontend/dist` ausente) instala deps se faltarem, gera o build, sobe em 127.0.0.1:8765 e abre o navegador já autenticado; `curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8765/` → `200` e o HTML contém `<div id="root">` | feature |
| T5 | CSP não quebra o app | no Chrome headless em `http://127.0.0.1:8765/?token=...`, abrir notebook e executar `1+1` → saída `2` e 0 violações de CSP no console | constraint |
| T5 | Já em execução | 2º `./start.sh` com a porta 8765 ocupada pelo Notisbook → sai com mensagem contendo `já está rodando` e exit ≠ 0, sem matar o 1º | feature |
| T6 | Scripts antigos removidos | `git ls-files install-spark.sh start-jupyter.sh pyproject.toml` → vazio | feature |
| F5 | Código das células em JetBrains Mono | no console `getComputedStyle(document.querySelector('.cm-content')).fontFamily` começa com `"JetBrains Mono"`; após build, `ls frontend/dist/assets/ \| grep -i 'jetbrains-mono.*woff2'` encontra ≥ 1 arquivo | feature |
| F5 | Fonte sem CDN | `grep -rnE 'fonts\.(googleapis\|gstatic)\.com' frontend/src frontend/index.html` → vazio | constraint |
| T9 | Reconexão do WS não perde o fim da execução | `grep -n '"starting"' backend/src/notisbook/kernels/service.py` mostra `starting` na guarda de `execute`; `grep -n 'except Exception' backend/src/notisbook/kernels/service.py` cobre `_await_ready` com `log.exception` | bugfix |
| T9 | Sessão/job inexistente chega como 4404 | cliente WS com token+Origin válidos em `/api/sessions/inexistente/channel` e `/api/jobs/inexistente/events` → handshake 101 seguido de close code `4404` | bugfix |
| F6 | Fila destrava após reconexão com célula em execução | script ad-hoc com os módulos do frontend: executar `time.sleep(5)` + 2ª célula na fila, derrubar o socket durante a 1ª → 1ª termina `aborted`, 2ª recebe `execute_reply` `ok` | bugfix |
| F6 | `not_found` vira mensagem de sessão inexistente | com o backend reiniciado, a aba mostra estado `not_found` (não 8 tentativas de reconexão): `grep -n 'not_found' frontend/src/ws/session.ts frontend/src/state/kernel.ts` + execução do script acima com sessão apagada → `onEnd("not_found")` | bugfix |
| T9 | Comentários sem separador visual nem referência ao plano | `grep -rnE '^\s*(#\|//) ?-{2,}' backend/src frontend/src` → vazio; `grep -rnE '(#\|//\|\*).*\b(D[0-9]{1,2}\|F[1-6]\|T[1-9]\|MVP)\b' backend/src frontend/src` → vazio | refactor |
| F6 | Reply atrasado não trava a fila após restart/morte do kernel | `grep -n 'staleReply' frontend/src/state/kernel.ts` mostra `staleReply` zerado no tratamento de `restarting`/`dead` de `onKernelState`; `npx --prefix frontend tsc --noEmit -p frontend` → exit 0 | bugfix |

## Arquivos previstos
- `backend/pyproject.toml` — T1, T2, T3, T4
- `backend/uv.lock` — T1, T2, T3, T4
- `backend/.python-version`, `backend/.gitignore` — T1
- `backend/src/notisbook/__init__.py`, `backend/src/notisbook/api/__init__.py` — T1
- `backend/src/notisbook/__main__.py` — T1
- `backend/src/notisbook/app.py` — T1, T2, T3, T4, T7, T5
- `backend/src/notisbook/config.py` — T1, T4
- `backend/src/notisbook/security.py` — T1
- `backend/src/notisbook/api/system.py` — T1, T4
- `backend/src/notisbook/notebooks/__init__.py`, `backend/src/notisbook/notebooks/store.py` — T2
- `backend/src/notisbook/api/contents.py` — T2
- `backend/src/notisbook/kernels/__init__.py`, `backend/src/notisbook/kernels/service.py` — T3
- `backend/src/notisbook/kernels/protocol.py` — T3
- `backend/src/notisbook/api/sessions.py` — T3
- `backend/src/notisbook/spark/__init__.py`, `backend/src/notisbook/spark/prereqs.py` — T4
- `backend/src/notisbook/spark/catalog.py` — T4
- `backend/src/notisbook/spark/installer.py` — T4
- `backend/src/notisbook/spark/kernelspec.py` — T4
- `backend/src/notisbook/jobs.py` — T4
- `backend/src/notisbook/api/spark.py` — T4
- `backend/src/notisbook/api/jobs.py` — T4
- `backend/src/notisbook/spark/catalog.py`, `backend/src/notisbook/api/spark.py`, `backend/src/notisbook/config.py` — T7
- `backend/src/notisbook/spark/prereqs.py`, `backend/src/notisbook/spark/installer.py`, `backend/src/notisbook/spark/kernelspec.py`, `backend/src/notisbook/api/system.py` — T8
- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html` — F1
- `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/lib/**`, `frontend/.gitignore`, `frontend/package-lock.json`, `frontend/src/api/**`, `frontend/src/ws/**`, `frontend/src/state/**`, `frontend/src/styles/**` — F1
- `frontend/src/components/files/**`, `frontend/src/components/shell/**` — F1
- `frontend/src/components/notebook/**`, `frontend/src/state/notebook.ts`, `frontend/src/state/router.ts`, `frontend/src/components/outputs/Markdown.tsx`, `frontend/src/components/outputs/Markdown.module.css`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/App.tsx` — F2
- `frontend/src/components/outputs/**`, `frontend/src/components/kernel/**`, `frontend/src/state/kernel.ts`, `frontend/src/api/http.ts`, `frontend/src/api/kernels.ts`, `frontend/src/App.tsx`, `frontend/package.json`, `frontend/package-lock.json` — F3
- `frontend/src/components/spark/**`, `frontend/src/components/settings/**`, `frontend/src/components/kernel/**`, `frontend/src/state/workspace.ts` — F4
- `frontend/src/components/shell/**`, `frontend/src/components/notebook/**`, `frontend/src/components/data/**`, `frontend/src/components/files/**`, `frontend/src/components/kernel/**`, `frontend/src/components/settings/**`, `frontend/src/components/outputs/Outputs.module.css`, `frontend/src/state/**`, `frontend/src/styles/**`, `frontend/src/lib/paths.ts`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/package.json`, `frontend/package-lock.json` — F5
- `start.sh`, `backend/src/notisbook/static.py`, `backend/src/notisbook/app.py`, `backend/src/notisbook/config.py` — T5
- `install-spark.sh`, `start-jupyter.sh`, `pyproject.toml` (remoção) — T6
- `.claude/plans/current/20261105_main_notisbook-mvp-react.md`, `.claude/plans/INDEX.md`, `.claude/plans/pendencias/TODO-notisbook-mvp-react.md` — orquestração
- `Notisbook.iml` — exceção do operador (ver `## Não mexer`)
- `backend/src/notisbook/kernels/service.py`, `backend/src/notisbook/api/sessions.py`, `backend/src/notisbook/api/jobs.py`, `backend/src/notisbook/security.py`, `backend/src/**/*.py` (comentários) — T9
- `frontend/src/ws/**`, `frontend/src/state/kernel.ts`, `frontend/src/**` (comentários) — F6

## Fora de escopo
- Autocomplete/inspect, buffer de saídas p/ reconexão, KaTeX, link p/ Spark UI, tabela de resultados interativa (exige dados estruturados do backend), barra de progresso de jobs Spark (API do Spark UI :4040), `update_display_data`, CurveZMQ nos kernels, kill de kernels órfãos após SIGKILL — fase 2.
- Painel Dados funcional: seleção de diretório, árvore/preview de arquivos (Files) e listagem de tabelas Spark/Hive (Catalog) — próxima etapa (D13).
- Tauri, ipywidgets, JS arbitrário em saídas, `input()`, Linux — fase 3.
- Testes automatizados persistidos — não pedidos; critérios são comandos executados na verificação.
- **Documentação de produto** — nenhuma (o repo não tem README/ARCHITECTURE). Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- Nomes de kernel `spark359` e `spark430` (compatibilidade com o Jupyter clássico).
- `.idea/` e `Notisbook.iml` — exceção nomeada: o operador ordenou "commit de tudo" em 2026-11-05 e o `Notisbook.iml` (fontes `backend`, `backend/src`, exclusão `backend/.venv`, alterado pelo IDE) foi incluído no commit 07ed313 por decisão dele.
- Bind fora de `127.0.0.1` (nenhuma opção `0.0.0.0` no MVP).

## Checkpoint

Atualizado: 2026-11-05 10:54:51 -0300. Baseline congelado: `e03954f` (commit inicial). Branch: `main`.

| Tn | estado | commit(s) |
|----|--------|-----------|
| T1 | concluída | d8800e8 |
| T2 | concluída | e75cbc2 |
| T3 | concluída | c1f26a6 |
| T4 | concluída | 30eb38d, 7573db4 |
| T7 | concluída | afb6cca |
| T8 | concluída | d0f50c3 |
| F1 | concluída (retomada após 1ª execução FAILED por erro de rede) | 39b6262, c0c4503, da0eabb |
| F2 | concluída | da7f9c2, 039a69e, c9044df |
| F3 | concluída | 18bf332, ac22a6d |
| F5 | concluída | e9739e0, 29aa831 |
| T5 | concluída | 295df44 |
| F4 | concluída | d387a64, 03f77b9, 0fb5176 |
| T6 | concluída | 750fa24 |
| — | review rodada 1: ajustes necessários (1 major, 4 minor, 6 nit → pendencias/); auditoria: DIVERGENTE [constraints] → exceção do operador registrada | 07ed313 |
| T9 | concluída | c09c2f0, f825dbf |
| F6 | concluída (rodada 2: 1 minor corrigido; rodada 3: review **aprovar**) | 64cfe62, 35e8c98, b9445c4 |

Pendências abertas (não bloqueiam):
- `Notisbook.iml`: operador decidiu incluí-lo ("commit de tudo") — commit 07ed313; exceção registrada em `## Não mexer`.
- Commits 30eb38d/7573db4 com trailer `Claude Sonnet 5.5` — mantidos (reescrever histórico exige autorização).
- `ruff` I001 em `backend/src/notisbook/api/sessions.py` — cosmético; esperado no code review.
- JDK 21 resolvido é o JetBrains Runtime (IntelliJ); Temurin 21 recomendado ao operador.
- Kernelspecs reais `spark359`/`spark430` do operador intactos; só passam a usar D9 se reinstalados pela app.
- Context7 indisponível nas sessões dos engineers — APIs confirmadas empiricamente.
- T5 precisa de fallback SPA para `/tree/*`, `/notebooks/*`, `/spark`, `/settings`.
- Operador testa a 1ª versão visual (F1+F2) em modo dev, fora do harness; achados viram ajuste no plano.
- Kernel legado `~/spark-notebooks/.venv-spark359` sem `distutils` (Python 3.12) quebra `toPandas()` — operador adiou; avaliar instalar `setuptools`/`pandas`/`pyarrow` nos envs criados pela app (T4) depois.
- Vite dev escuta só em `localhost` (IPv6 ::1); some com T5.
- Fechar o navegador à força deixa sessão de kernel viva até o shutdown do servidor (fase 2).
- Operador aprovou o visual F5 ("excelente") e pediu abertura autônoma: T5 antecipada para antes de F4.
- Fechamento: review rodada 3 **aprovar**; auditoria rodada 2 **CONFORME** (62/62). Commit automático cc3dd23; validado pelo operador ("finalize o plano"); memória de projeto gravada; plano fechado.
- Backend reenvia o `execute_reply` órfão pela nova conexão (contra a garantia declarada em T9); tratado no frontend (F6).
- `DELETE /api/sessions/<id>` não fecha o WS já aberto; 4404 só na próxima conexão.
- Ao retomar: code review (§ 4.05) + plan-auditor (§ 4.06) só ao fim de T6, com o baseline acima.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T7  - [x] T8  - [x] F1  - [x] F2  - [x] F3  - [x] F5  - [x] F4  - [x] T5  - [x] T6  - [x] T9  - [x] F6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | software-architect | OK | 225220 | 47478 |
| 1 | python-engineer | OK | 54692 | 34956 |
| 2 | python-engineer | OK | 121752 | 45510 |
| 3 | python-engineer | OK | 473556 | 79457 |
| 4 | python-engineer | OK | 282526 | 90217 |
| 5 | python-engineer | OK | 137843 | 55556 |
| 6 | python-engineer | OK | 842958 | 59691 |
| 7 | general-purpose | FAILED | — | — |
| 7 | general-purpose | OK | 295276 | 110855 |
| 8 | general-purpose | OK | 477288 | 127055 |
| 9 | general-purpose | OK | 650685 | 160364 |
| 10 | general-purpose | OK | 926751 | 223049 |
| 11 | python-engineer | OK | 108412 | 54476 |
| 12 | general-purpose | OK | 683903 | 136670 |
| 13 | python-engineer | OK | 14795 | 26477 |
| 14 | general-purpose (code-review) | OK | 177210 | 151940 |
| 14 | plan-auditor | OK | 73776 | 41021 |
| 15 | python-engineer | OK | 207558 | 46881 |
| 16 | general-purpose | OK | 500390 | 138885 |
| 17 | general-purpose (evidência) | OK | 1158341 | 197562 |
| 17 | general-purpose (code-review r2) | OK | 178545 | 127302 |
| 18 | general-purpose | OK | 194480 | 73339 |
| 18 | general-purpose (code-review r3) | OK | 72048 | 82042 |
| 18 | plan-auditor | OK | 103170 | 82323 |
| 19 | memory-manager | OK | 22316 | 40208 |
| 19 | memory-manager | OK | 14368 | 38591 |
<!-- effort-ledger:end -->
