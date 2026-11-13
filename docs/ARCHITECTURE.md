# Arquitetura do Notisbook

## Pré-requisitos

- Leitura básica de Python (FastAPI), TypeScript (React) e do modelo de kernels Jupyter.
- Os caminhos citados são relativos à raiz do repositório. Diagramas em Mermaid ficam em `docs/arch/`.

## Visão geral

O Notisbook é uma aplicação monousuário que roda inteiramente na máquina local. Um único processo Python (FastAPI sobre Uvicorn) serve a interface web compilada, expõe uma API REST/WebSocket restrita ao loopback e gerencia processos de kernel IPython via `jupyter_client`. Ambientes Spark são criados com `uv` sob a pasta de dados do Notisbook, e um catálogo SQLite persiste bancos e tabelas entre sessões.

| Diagrama | Arquivo |
|---|---|
| Contexto | [docs/arch/context.mmd](arch/context.mmd) |
| Containers | [docs/arch/container.mmd](arch/container.mmd) |
| Componentes do backend | [docs/arch/component.mmd](arch/component.mmd) |
| Implantação | [docs/arch/deployment.mmd](arch/deployment.mmd) |
| Fluxo de dados | [docs/arch/data-flow.mmd](arch/data-flow.mmd) |

## Estrutura observada

| Caminho | Natureza |
|---|---|
| `backend/pyproject.toml`, `backend/uv.lock` | Manifesto do pacote Python `notisbook` (build `hatchling`, script `notisbook`) |
| `backend/src/notisbook/` | Código do backend |
| `backend/src/notisbook/samples/` | Notebooks de exemplo empacotados (Delta, Iceberg, Hudi) |
| `frontend/` | SPA React + Vite + TypeScript (`frontend/package.json`, `frontend/vite.config.ts`) |
| `scripts/build_release.py` | Build do frontend, cópia para o pacote e geração de sdist/wheel |
| `scripts/release.sh` | Versão, tag, release no GitHub e atualização da fórmula Homebrew |
| `start.sh` | Execução a partir do código-fonte |

## Módulos do backend

| Módulo | Responsabilidade | Evidência |
|---|---|---|
| CLI | Argumentos `--port`, `--root`, `--no-browser`, `--version`; prepara a pasta de dados, o catálogo e o onboarding; sobe o Uvicorn | `backend/src/notisbook/__main__.py` |
| Configuração | `Settings` imutável: host fixo, porta, pasta de dados, token, origens e hosts permitidos | `backend/src/notisbook/config.py` |
| Fábrica da aplicação | Cria o `FastAPI`, registra routers e estado compartilhado; `lifespan` limpa órfãos e encerra kernels/instalador | `backend/src/notisbook/app.py` |
| Segurança | Token (Bearer, cookie ou `?token=`), guarda de Host e de Origin para WebSocket | `backend/src/notisbook/security.py` |
| Frontend estático | `/assets`, fallback SPA e cabeçalho CSP | `backend/src/notisbook/static.py` |
| API | Routers `system`, `contents`, `export`, `files`, `notebooks_root`, `sessions`, `variables`, `catalog`, `spark`, `jobs` | `backend/src/notisbook/api/` |
| Armazenamento de notebooks | Leitura/gravação sob uma raiz única, com escrita atômica | `backend/src/notisbook/notebooks/store.py` |
| Preferências | `<dados>/preferences.json` (raiz dos notebooks, marcador `samples_seeded`) e validação da raiz | `backend/src/notisbook/preferences.py` |
| Onboarding | Primeira execução: pasta padrão de notebooks e cópia dos exemplos | `backend/src/notisbook/onboarding.py` |
| Kernels | Sessões sobre `jupyter_client`, protocolo WebSocket v1, células SQL/DuckDB, sondas de variáveis, hook de catálogo | `backend/src/notisbook/kernels/` |
| Spark | Pré-requisitos (uv, JDK), catálogo de versões via PyPI, instalador, matriz de bundles, kernelspecs, pacotes `uv pip` | `backend/src/notisbook/spark/` |
| Catálogo | `catalog.db` (SQLite): registro `nb_*` e tabelas do Iceberg `JdbcCatalog` | `backend/src/notisbook/catalog/` |
| Jobs | Registro em memória de tarefas longas com log de eventos reproduzível | `backend/src/notisbook/jobs.py` |
| Arquivos | Listagem de diretórios por caminho absoluto (só metadados) e seletor nativo de pasta | `backend/src/notisbook/files/` |
| Exportação | Conversores puros para `.py` (Databricks), `.ipynb` e HTML | `backend/src/notisbook/export/` |
| Salvaguardas de exclusão | Proteção de caminhos e remoção recursiva com erro parcial explícito | `backend/src/notisbook/fs_safety.py` |

## Frontend

- React 19 com estado em Zustand, editor CodeMirror (Python, SQL, Markdown), Markdown via `marked`, saídas ANSI via `ansi_up` e sanitização com DOMPurify (`frontend/package.json`).
- Clientes REST em `frontend/src/api/` e WebSocket em `frontend/src/ws/` (sessões de kernel e eventos de jobs), com reconexão por backoff exponencial limitado (`frontend/src/ws/socket.ts`).
- Saídas HTML de células são sanitizadas com DOMPurify e renderizadas em Shadow DOM (`frontend/src/components/outputs/HtmlOutput.tsx`, `frontend/src/components/outputs/purify.ts`).
- Em desenvolvimento, o Vite (porta 5173) faz proxy de `/api` para `http://127.0.0.1:8765`, reescreve o Origin do upgrade WebSocket e recusa upgrades cujo Origin não seja o próprio dev server (`frontend/vite.config.ts`).

## Dependências

### Backend (`backend/pyproject.toml`)

`fastapi`, `uvicorn[standard]`, `jupyter-client`, `nbformat`, `markdown-it-py`, `nh3`, `pygments`, `psutil`, `packaging`. Python `>=3.12`.

### Instaladas nos ambientes Spark (`backend/src/notisbook/spark/installer.py`)

`pyspark==<versão escolhida>`, `ipykernel`, `duckdb==2.0.0` e o pacote `delta-spark` da linha, com Python 3.12 provisionado por `uv python install`.

### Matriz de bundles (`backend/src/notisbook/spark/bundles.py`)

| Linha Spark | Formatos | Jars (Maven) |
|---|---|---|
| 3.5.0 a 3.5.2 | delta, iceberg, hudi | `delta-spark_2.12` 3.2.0, `delta-storage`, `iceberg-spark-runtime-3.5_2.12`, `hudi-spark3.5-bundle_2.12` |
| 3.5 (demais patches) | delta, iceberg, hudi | `delta-spark_2.12` 3.3.3, `delta-storage`, `iceberg-spark-runtime-3.5_2.12`, `hudi-spark3.5-bundle_2.12` |
| 4.1 | delta, iceberg, hudi | `delta-spark_2.13` 4.1.0, `delta-storage`, `iceberg-spark-runtime-4.1_2.13`, `hudi-spark4.1-bundle_2.13` |

Todo jar tem sha256 fixado; `sqlite-jdbc` (`org.xerial`) dá ao Iceberg acesso ao `catalog.db`. Versões sem entrada na matriz não recebem bundle.

### Serviços externos acessados

| Serviço | Uso | Evidência |
|---|---|---|
| PyPI (JSON API, padrão `https://pypi.org`) | Catálogo de versões estáveis do `pyspark` (cache de 1 h, com fallback) e índice para `uv pip` | `backend/src/notisbook/spark/catalog.py`, `backend/src/notisbook/spark/packages.py`, `backend/src/notisbook/config.py` |
| Maven Central (padrão `https://repo1.maven.org/maven2`) | Download dos jars dos bundles | `backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/spark/installer.py` |
| `uv` | Provisionamento de Python, venvs e pacotes | `backend/src/notisbook/spark/installer.py` |
| JDK local (`/usr/libexec/java_home`, `$JAVA_HOME`, keg `openjdk@<major>` do Homebrew) | `JAVA_HOME` dos kernels Spark | `backend/src/notisbook/spark/prereqs.py` |
| `osascript` (macOS) | Diálogo nativo de escolha de pasta | `backend/src/notisbook/files/native_picker.py` |

A origem de onde o `uv` baixa o interpretador Python: Não identificado no código analisado (é comportamento da ferramenta `uv`).

## Configuração

| Variável / parâmetro | Efeito | Evidência |
|---|---|---|
| `NOTISBOOK_HOME` | Pasta de dados; padrão `~/.notisbook`. Contém `envs/`, `warehouse/`, `catalog.db`, `preferences.json` e `notebooks/` | `backend/src/notisbook/config.py`, `backend/src/notisbook/preferences.py` |
| `NOTISBOOK_FRONTEND_DIST` | Diretório do frontend compilado; senão `frontend/dist` do repositório, senão `_frontend` embutido no pacote | `backend/src/notisbook/config.py` |
| `NOTISBOOK_PYPI_URL` | Base da API do PyPI (espelhos/offline) | `backend/src/notisbook/config.py` |
| `NOTISBOOK_MAVEN_URL` | Base do repositório Maven para os jars | `backend/src/notisbook/spark/bundles.py` |
| `NOTISBOOK_JAVA_HOME_TOOL` | Substitui o executável `java_home` (ponto de teste) | `backend/src/notisbook/spark/prereqs.py` |
| `JAVA_HOME`, `HOMEBREW_PREFIX` | Seleção do JDK | `backend/src/notisbook/spark/prereqs.py` |
| `JUPYTER_DATA_DIR` | Local dos kernelspecs do usuário | `backend/src/notisbook/spark/kernelspec.py` |
| `--port` | Porta HTTP; padrão `8765` | `backend/src/notisbook/__main__.py`, `backend/src/notisbook/config.py` |
| `--root` | Raiz dos notebooks; quando informada, trava a troca pela interface | `backend/src/notisbook/__main__.py`, `backend/src/notisbook/api/notebooks_root.py` |
| `--no-browser` | Não abre o navegador | `backend/src/notisbook/__main__.py` |

O host de escuta é sempre `127.0.0.1` e não é configurável (`backend/src/notisbook/config.py`).

### Raiz dos notebooks e pasta padrão

A raiz inicial segue a precedência `--root` > preferência salva válida > `<dados>/notebooks` (`backend/src/notisbook/__main__.py`, função `_resolve_root`). A validação recusa caminhos relativos, inexistentes, sem permissão de leitura/escrita, a raiz `/`, o home do usuário, a pasta de dados e seus ancestrais; a única exceção dentro da pasta de dados é `<dados>/notebooks` e seus descendentes (`backend/src/notisbook/preferences.py`, `validate_notebooks_root`).

### Onboarding da primeira execução

`run_onboarding` roda depois de `ensure_home` e antes da leitura das preferências; não faz nada com `--root` ou quando `preferences.json` já existe (`backend/src/notisbook/onboarding.py`). Caso contrário:

1. Com a pasta de dados padrão (sem `NOTISBOOK_HOME`), adota `~/notebooks` se ela contiver ao menos um `.ipynb` visível e passar na validação.
2. Senão, copia `backend/src/notisbook/samples/*.ipynb` (`delta.ipynb`, `iceberg.ipynb`, `hudi.ipynb`) para `<dados>/notebooks`, sem sobrescrever arquivos existentes (temporário oculto + `os.link`), com modo `0600`, e grava o marcador `samples_seeded`.
3. O marcador impede recriar exemplos apagados pela pessoa usuária; qualquer falha vira aviso no stderr e a próxima partida tenta de novo.

## Fluxos de dados

### Partida

`main` → `ensure_home` (cria `<dados>`, `envs/`, `warehouse/`) → `ensure_catalog_db` → `run_onboarding` → `_resolve_root` → impressão da URL com token → `uvicorn.run` em `127.0.0.1` com access log desligado (`backend/src/notisbook/__main__.py`). No `lifespan`, a aplicação remove arquivos de conexão órfãos da execução anterior na mesma porta e varre a lixeira de ambientes (`backend/src/notisbook/app.py`, `backend/src/notisbook/kernels/service.py`).

### Notebooks

A SPA usa `/api/contents` para listar, ler, salvar, criar, renomear e excluir. Gravações usam escrita atômica (temporário + `fsync` + `os.replace`) e todos os caminhos são resolvidos dentro da raiz; symlinks que apontam para fora respondem 403 (`backend/src/notisbook/notebooks/store.py`). Rotas de escrita exigem o cabeçalho `X-Notisbook-Root-Generation` coerente com a geração atual quando enviado; divergência responde 409 `root_changed` (`backend/src/notisbook/api/notebooks_root.py`).

### Execução de células

1. `POST /api/sessions` inicia um kernel pelo kernelspec escolhido (`backend/src/notisbook/api/sessions.py`).
2. A SPA abre `/api/sessions/{session_id}/channel` (WebSocket, protocolo v1): cliente envia `execute`, `interrupt`, `restart`; servidor envia `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error` (`backend/src/notisbook/kernels/protocol.py`).
3. Células `sql` e `duckdb` são transformadas em código Python que usa um módulo oculto de renderização (`_notisbook_display`) no kernel (`backend/src/notisbook/kernels/sql_cell.py`).
4. Saídas de stream são limitadas a 1.000.000 bytes por célula (`backend/src/notisbook/kernels/service.py`, `STREAM_LIMIT_BYTES`).

### Catálogo

- O backend é o único que cria/altera o esquema do `catalog.db` (tabelas `nb_*` e `iceberg_*`) (`backend/src/notisbook/catalog/store.py`).
- Nos kernels, o módulo oculto `_notisbook_catalog` intercepta `SparkSession.Builder.getOrCreate`/`stop`, hidrata a sessão a partir do registro `nb_*` e reconcilia criações, alterações e remoções após cada célula (`backend/src/notisbook/kernels/catalog_hook.py`).
- O catálogo `iceberg` do Spark é um `JdbcCatalog` apontando para o mesmo `catalog.db`, com warehouse em `<dados>/warehouse/iceberg` (`backend/src/notisbook/spark/bundles.py`).
- `/api/catalog` lê bancos, tabelas e colunas e cria/exclui schemas sem `SparkSession`; a exclusão apaga linhas em transação `BEGIN IMMEDIATE` e só depois remove pastas MANAGED (`backend/src/notisbook/catalog/schemas.py`).

### Instalação de ambientes Spark

`POST /api/spark/versions` cria um job (`backend/src/notisbook/api/spark.py`). O instalador verifica `uv` e JDK, instala Python 3.12, cria `<dados>/envs/spark-<versão>-<id>/`, instala pacotes, grava a configuração `log4j2`, baixa e verifica os jars, valida `pyspark` e `duckdb`, grava o kernelspec e só então remove o ambiente anterior (`backend/src/notisbook/spark/installer.py`). O progresso é transmitido por `/api/jobs/{job_id}/events` (WebSocket) (`backend/src/notisbook/api/jobs.py`, `backend/src/notisbook/jobs.py`).

### Exportação

`POST /api/export/{fmt}` com `fmt` em `py`, `ipynb` ou `html` converte o notebook enviado no corpo; nada é lido nem gravado em disco, e o corpo é limitado a 50 MB (413 acima disso) (`backend/src/notisbook/api/export.py`). O relatório HTML não tem JavaScript e sanitiza o conteúdo com `nh3` (`backend/src/notisbook/export/html_report.py`).

## Empacotamento e distribuição

1. `scripts/build_release.py` compila o frontend (`npm ci`, `npm run build`), copia `frontend/dist` para `backend/src/notisbook/_frontend`, executa `uv build --sdist --wheel` e confere que `index.html` está nos dois artefatos.
2. `backend/pyproject.toml` inclui `_frontend` (gitignorado) como `artifacts` no wheel e no sdist.
3. `scripts/release.sh` exige branch `main` limpa e sincronizada, versão maior que a atual, atualiza `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`/`package-lock.json`, cria commit e tag, publica a release no GitHub com o sdist, calcula o sha256 do asset baixado, atualiza `url`/`sha256` da fórmula `Formula/notisbook.rb` no tap `rom-mm/tap`, regenera `resources` Python somente se `uv.lock` mudou desde a tag anterior, valida com `brew reinstall --build-from-source`, `brew test` e `brew audit --strict` (salvo `--skip-brew-test`) e publica o tap. Há modo `--dry-run`.
4. `start.sh` executa a partir do código-fonte e detecta, via cabeçalho `X-Notisbook` em `/api/health`, se a porta já está ocupada por uma instância do Notisbook.

O conteúdo da fórmula Homebrew e pipelines de CI: Não identificado no código analisado.

## Controles de segurança

Controles configurados no código; não constituem garantia operacional verificada.

| Controle | Descrição | Evidência |
|---|---|---|
| Bind em loopback | Host fixo `127.0.0.1`, sem opção de configuração | `backend/src/notisbook/config.py` |
| Token de sessão | `secrets.token_urlsafe(32)` por processo; aceito como Bearer, cookie `notisbook_token` ou `?token=`; comparação em tempo constante | `backend/src/notisbook/config.py`, `backend/src/notisbook/security.py` |
| Cookie | `HttpOnly`, `SameSite=Strict`, definido quando o token chega por query | `backend/src/notisbook/security.py` |
| Trusted host | Rejeita `Host` fora de `127.0.0.1:<porta>`/`localhost:<porta>` (proteção contra DNS rebinding) em `files`, `catalog`, `variables`, `notebooks-root` e `system/resources` | `backend/src/notisbook/security.py`, `backend/src/notisbook/api/` |
| Guarda de WebSocket | Token, `Origin` e `Host` validados antes do `accept()`; recusa com código 1008 | `backend/src/notisbook/security.py` |
| Access log desligado | Evita que o token em `?token=` vá para o stdout | `backend/src/notisbook/__main__.py` |
| CSP | `default-src 'self'`, `script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`; `style-src` com `'unsafe-inline'` por exigência do CodeMirror e do Shadow DOM | `backend/src/notisbook/static.py` |
| Sem docs da API em produção | `docs_url`, `redoc_url` e `openapi_url` desativados | `backend/src/notisbook/app.py` |
| Contenção de caminhos | Notebooks resolvidos dentro da raiz; symlink para fora responde 403; fallback SPA só serve arquivos dentro de `dist` | `backend/src/notisbook/notebooks/store.py`, `backend/src/notisbook/static.py` |
| Caminhos protegidos | Home do usuário e pasta de dados (e seus ancestrais) não podem virar raiz nem ser apagados; exclusão de pasta é recusada com kernel aberto ou tabelas de catálogo dentro dela | `backend/src/notisbook/preferences.py`, `backend/src/notisbook/fs_safety.py`, `backend/src/notisbook/api/files.py` |
| Integridade de downloads | sha256 fixado por jar; só esquemas `http`/`https` | `backend/src/notisbook/spark/installer.py`, `backend/src/notisbook/spark/bundles.py` |
| Pacotes restritos | Nome/especificador validados (PEP 508/440), URL, caminho, extras e marcadores recusados; `uv` com `--no-config` e índice fixo; subprocessos só por lista de argumentos | `backend/src/notisbook/spark/requirements.py`, `backend/src/notisbook/spark/packages.py` |
| Seletor nativo | Script AppleScript constante; argumentos passados por `argv`, sem interpolação | `backend/src/notisbook/files/native_picker.py` |
| Sanitização de HTML | DOMPurify nas saídas da SPA; `nh3` no relatório exportado | `frontend/src/components/outputs/purify.ts`, `backend/src/notisbook/export/html_report.py` |
| Permissões de arquivos | `preferences.json` e exemplos semeados com modo `0600` | `backend/src/notisbook/preferences.py`, `backend/src/notisbook/onboarding.py` |

Observação: as páginas da SPA são públicas por desenho; a autenticação acontece nas rotas `/api` (`backend/src/notisbook/static.py`). `/api/contents`, `/api/sessions`, `/api/spark`, `/api/jobs` e `/api/export` exigem token, mas não aplicam `require_trusted_host` (`backend/src/notisbook/api/`).

## Resiliência

| Mecanismo | Evidência |
|---|---|
| Instalação Spark transacional por diretório: falha ou cancelamento descarta o ambiente novo e preserva o kernelspec anterior | `backend/src/notisbook/spark/installer.py` |
| Catálogo de versões com cache de 1 h e fallback para o último catálogo válido ou lista estática | `backend/src/notisbook/spark/catalog.py` |
| Escrita atômica de notebooks e preferências (temporário + `fsync` + `os.replace`) | `backend/src/notisbook/notebooks/store.py`, `backend/src/notisbook/preferences.py` |
| Preferências malformadas são ignoradas com aviso; preferência salva inválida cai na pasta padrão | `backend/src/notisbook/preferences.py`, `backend/src/notisbook/__main__.py` |
| SQLite com `busy_timeout` (5 s no backend, 10 s no JDBC do Iceberg) para concorrência entre kernels | `backend/src/notisbook/catalog/store.py`, `backend/src/notisbook/spark/bundles.py` |
| Remoção de arquivos de conexão órfãos e encerramento de kernels/instalador no ciclo de vida | `backend/src/notisbook/app.py`, `backend/src/notisbook/kernels/service.py` |
| Espera de prontidão do kernel com timeout de 60 s | `backend/src/notisbook/kernels/service.py` |
| Reconexão WebSocket com backoff exponencial limitado no cliente | `frontend/src/ws/socket.ts` |
| Falhas de partida da pasta de dados ou do catálogo encerram com mensagem clara; falha de onboarding só gera aviso | `backend/src/notisbook/__main__.py`, `backend/src/notisbook/onboarding.py` |

Métricas de desempenho, limites de capacidade e observabilidade (métricas/tracing): Não identificado no código analisado.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
