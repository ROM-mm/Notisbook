# Arquitetura do Notisbook

## Pré-requisitos

- macOS em Apple Silicon (`darwin-arm64`). O instalador recusa outras plataformas (`install.sh`), e o MinIO e as extensões DuckDB exigem arm64 (`backend/src/notisbook/platform_support.py`).
- Python `>=3.12` (`backend/pyproject.toml`), gerenciado pelo `uv` na instalação (`uv tool install --python 3.12 --managed-python`).
- JDK 17 ou 21 para os runtimes Spark locais (`backend/src/notisbook/spark/prereqs.py`).
- Docker (por exemplo, Colima) apenas para o runtime AWS Glue.
- Para desenvolvimento: `uv`, `node` e `npm` (`start.sh`).

Os caminhos citados neste documento são relativos à raiz do repositório. `notisbook/` abrevia `backend/src/notisbook/`.

## 1. Visão geral

O Notisbook é uma estação de dados local: uma aplicação de notebooks que roda inteira na máquina da pessoa usuária, com runtimes Spark, DuckDB e AWS Glue (em Docker) e um data lake local em MinIO.

A aplicação é **um único processo Python** (FastAPI + uvicorn). Esse processo:

- serve a SPA React já compilada e a API REST/WebSocket na mesma origem;
- gerencia kernels Jupyter via `jupyter_client`;
- instala e versiona os ambientes de execução (Spark, DuckDB e Glue);
- supervisiona um processo MinIO local;
- expõe um catálogo Iceberg REST, usado pelos kernels Docker e DuckDB.

Tudo escuta só em loopback (`127.0.0.1`). O host está fixado em `notisbook/config.py` (`HOST = "127.0.0.1"`), sem opção de configuração.

## 2. Estrutura do repositório

| Caminho | Conteúdo |
|---|---|
| `backend/src/notisbook/` | backend Python: CLI, app FastAPI, kernels, runtimes, catálogo, notislake |
| `frontend/` | SPA React 19 + TypeScript + Vite |
| `scripts/` | `release.sh`, `build_release.py`, `build_minio.py`, `clean.py` |
| `install.sh` | instalador publicado como asset da release |
| `start.sh` | execução em desenvolvimento |
| `site/` | landing page estática, publicada no GitHub Pages (`.github/workflows/pages.yml`) |

## 3. Processo e ciclo de vida

### 3.1 Ponto de entrada

O script de console `notisbook` aponta para `notisbook.__main__:main` (`backend/pyproject.toml`).

- **Flags do servidor:** `--port` (padrão `8765`, `notisbook/config.py`), `--root`, `--no-browser`, `--check-notislake`, `--stop-running`.
- **Subcomandos:** `update [--version X.Y.Z]` e `uninstall [--yes]` (`notisbook/maintenance/`).

### 3.2 Subida (`notisbook/__main__.py`, `_serve`)

1. Cria a raiz de dados e prepara e migra o `catalog.db`.
2. Roda o onboarding (cópia dos notebooks de exemplo).
3. Resolve a raiz dos notebooks, nesta ordem: `--root` (que trava a troca pela UI), a preferência salva, `<home>/notebooks`.
4. **Troca de versão:** lê `<home>/run/backend.json`.
   - Se a instância viva for de outra versão, pede `POST /api/lifecycle/shutdown` com o token de lifecycle e espera até 60 s.
   - Se for da mesma versão, encerra com erro.
5. Abre o socket em `127.0.0.1:<porta>` antes do uvicorn. Porta ocupada encerra o processo.
6. Inicia o supervisor do MinIO.
7. Grava `backend.json` (pid, porta, versão e token de lifecycle; modo 0600, escrita atômica).
8. Imprime a URL `http://127.0.0.1:<porta>/?token=…` e abre o navegador.
9. Executa o uvicorn com `access_log=False`, porque o token trafega na query.

O lifespan do app (`notisbook/app.py`) limpa os resíduos na subida: connection files órfãos, kernelspecs órfãos, containers e imagens Docker com o label de dono e pastas `.trash-*`.

### 3.3 Encerramento

- SIGTERM e SIGHUP acionam o encerramento ordenado.
- O lifespan para installers, sessões de kernel e runtimes Docker.
- Um fallback síncrono roda `docker stop -t 10` nos containers do app, com orçamento de 20 s.
- Por fim, o MinIO é parado (SIGTERM, 10 s, SIGKILL) e `backend.json` é removido.

## 4. Backend — componentes

| Subpacote | Responsabilidade | Arquivos-chave |
|---|---|---|
| raiz | CLI, fábrica do app, configuração, segurança, SPA, jobs, preferências, onboarding | `__main__.py`, `app.py`, `config.py`, `security.py`, `static.py`, `jobs.py` |
| `api/` | routers FastAPI (seção 5) | 17 routers |
| `kernels/` | sessões `jupyter_client`, protocolo WebSocket, módulos injetados no kernel | `service.py`, `protocol.py`, `catalog_hook.py`, `sql_cell.py`, `languages.py` |
| `spark/` | matriz de bundles, instalador via uv, kernelspec, cache de jars, JDK, catálogo PyPI, libs | `bundles.py`, `installer.py`, `kernelspec.py`, `jar_cache.py`, `prereqs.py` |
| `runtimes/docker/` | runtime AWS Glue em container persistente | `service.py`, `launch.py`, `incontainer.py`, `catalog.py` |
| `runtimes/glue/` | Dockerfile da imagem e validador executado dentro do container | `Dockerfile`, `validate_runtime.py` |
| `runtimes/duckdb/` | ambiente DuckDB por versão e extensões offline | `installer.py`, `manifest.py`, `extensions.json`, `hook.py` |
| `catalog/` | `catalog.db`: registro `nb_*` e tabelas do Iceberg JdbcCatalog | `store.py`, `registry.py`, `iceberg_jdbc.py`, `schemas.py` |
| `notislake/` | MinIO local: binário, supervisor, credencial, layout medalhão, conexão S3 manual, opções S3A | `binary.py`, `supervisor.py`, `objectstore.py`, `sparkconf.py` |
| `notebooks/` | armazenamento de `.ipynb` isolado sob uma raiz | `store.py` |
| `files/`, `fonts/` | listagem de pastas, seletor nativo e fontes do macOS (via `osascript`) | `browser.py`, `native_picker.py`, `system_fonts.py` |
| `export/` | export `.py` (formato Databricks) e HTML autocontido | `py_source.py`, `html_report.py` |
| `maintenance/` | `update` (install.sh conferido por `SHA256SUMS`) e `uninstall` (preserva dados) | `update.py`, `uninstall.py` |

## 5. API HTTP e WebSocket

Os routers são registrados em `notisbook/app.py`. A documentação automática do FastAPI (`/docs`, `/redoc`, `/openapi.json`) está desligada. O contrato detalhado está em `docs/api/swagger.yaml`.

| Prefixo | Finalidade |
|---|---|
| `/api` (system) | health, pré-requisitos (uv/JDK), recursos da máquina, `/api/ws/ping` |
| `/api/contents` | CRUD de notebooks e pastas |
| `/api/notebooks-root` | ler e trocar a raiz dos notebooks |
| `/api/fs` | seletor de pasta, atalhos, listagem, exclusão de pasta |
| `/api` (sessions) | kernelspecs, sessões e canal WebSocket do kernel |
| `/api/catalog` | árvore do catálogo, tabelas, info e schemas |
| `/api/spark`, `/api/duckdb`, `/api/docker` | instalação, remoção e libs dos runtimes |
| `/api` (jobs) | estado do job e stream `/api/jobs/{id}/events` |
| `/api/notislake` | estado do MinIO, retry, credencial local, conexão S3 manual, listagem |
| `/api/export`, `/api/samples`, `/api/appearance` | export, exemplos e fontes |
| `/api/lifecycle` | shutdown ordenado (só loopback, com token próprio) |
| `/api/runtime-catalog`, `/iceberg` | rotas exclusivas dos kernels de runtime (seção 8.3) |

### 5.1 Protocolo do canal de kernel (v1)

Definido em `notisbook/kernels/protocol.py` e espelhado em `frontend/src/ws/protocol.ts`. Todo frame é JSON com `v: 1` e `type`.

- **Cliente → servidor:** `execute` (`cell_id`, `code`, `language` ∈ `python|sql|duckdb`), `interrupt`, `restart`.
- **Servidor → cliente:** `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error`.
- **Códigos de fechamento:** `4409` quando outra conexão assume a sessão; `4404` para sessão desconhecida.
- Ao reconectar, as saídas não são reenviadas: o primeiro frame é sempre `status`.

### 5.2 SPA

`notisbook/static.py` serve `/assets` e devolve `index.html` para as rotas da SPA, sempre com CSP. A pasta do frontend vem, nesta ordem, de `NOTISBOOK_FRONTEND_DIST`, `frontend/dist` (desenvolvimento) ou `notisbook/_frontend` (pacote).

## 6. Frontend

| Aspecto | Implementação |
|---|---|
| Stack | React 19, TypeScript (strict), Vite, Zustand (`frontend/package.json`) |
| Roteamento | store próprio sobre a History API (`frontend/src/state/router.ts`): `/`, `/tree/…`, `/notebooks/…`, `/settings`, `/settings/appearance` |
| Estado | um store de notebook e um de kernel **por aba** (`frontend/src/state/workspace.ts`, `notebook.ts`, `kernel.ts`) |
| Editor | CodeMirror 6, com Python, Spark SQL e Markdown |
| HTTP | `fetch` relativo a `/api` (`frontend/src/api/http.ts`) |
| WebSocket | `JsonSocket` com reconexão e backoff exponencial (`frontend/src/ws/socket.ts`) |

**Autenticação no navegador** (`frontend/src/api/auth.ts`): a página abre com `?token=`, chama `GET /api/health?token=…` (o backend grava o cookie `notisbook_token`, `httponly` e `samesite=strict`), retira o token da URL e o mantém só em memória para o cabeçalho `Authorization: Bearer`.

**Saídas de célula** (`frontend/src/components/outputs/`):

- `text/html` passa por DOMPurify e é anexado a um Shadow DOM, sem iframe e sem `script`.
- SVG é exibido via `<img>` com data URI, nunca inline.
- Markdown (`marked`) e texto ANSI (`ansi_up`) também passam por DOMPurify.
- Saídas JavaScript e ipywidgets não são renderizadas.

Em desenvolvimento, o Vite (porta `5173`) encaminha `/api` para `127.0.0.1:8765` e recusa upgrades WebSocket de outras origens (`frontend/vite.config.ts`).

## 7. Kernels e runtimes

### 7.1 Kernels

Só `notisbook/kernels/service.py` usa `jupyter_client`. Os kernelspecs ficam numa pasta exclusiva do app, `<home>/kernels`, com `ensure_native_kernel=False`: kernels de terceiros não aparecem.

| Runtime | Nome do kernel | Linguagens de célula |
|---|---|---|
| Spark local | `spark<versão sem pontos>` | python, sql, duckdb |
| AWS Glue (Docker) | `notisbook-docker-glue` | python, sql |
| DuckDB | `duckdb-<maj>-<min>-<patch>` | python, duckdb |

O backend valida a linguagem pedida contra o tipo do kernel. Ao iniciar uma sessão, um `execute` silencioso instala dois módulos ocultos:

- `_notisbook_display` (`kernels/sql_cell.py`): executa células SQL/DuckDB e renderiza tabelas, até 1000 linhas.
- `_notisbook_catalog` (`kernels/catalog_hook.py`): intercepta `SparkSession`, writers e `createTable` para manter o registro `nb_*` e aplicar o layout medalhão.

Limites: 1 MB de saída por célula e 60 s para o kernel ficar pronto.

### 7.2 Spark local

O instalador (`notisbook/spark/installer.py`) roda como job, nas fases `prereqs → python → venv → install → bundle → validate → kernelspec → cleanup`:

1. Cria um ambiente imutável com `uv` em `<home>/envs/spark-<versão>-<hash>`, com `pyspark`, `ipykernel` e `duckdb`.
2. Detecta a versão do Hadoop embutida e escolhe os jars S3A correspondentes.
3. Baixa os jars do bundle (Delta, Iceberg, Hudi, `sqlite-jdbc`) do Maven Central. Cada jar tem sha256 fixado em `spark/bundles.py`, e o cache é endereçado por conteúdo (`<home>/jars/<sha256>/`).
4. Roda um smoke test (até 300 s) e grava o kernelspec de forma atômica.

Se a instalação falhar, o ambiente novo é descartado e o anterior continua intacto.

O JDK é escolhido pela linha do Spark: 17 para Spark 3.x, 21 ou 17 para as demais (`spark/prereqs.py`).

**Rede do driver.** Todo `spark-defaults.conf` gerado por `render_base_defaults()` (`spark/bundles.py`) contém:

```
spark.sql.catalogImplementation in-memory
spark.driver.bindAddress 127.0.0.1
spark.driver.host 127.0.0.1
spark.ui.killEnabled false
```

O kernelspec define `SPARK_LOCAL_IP=127.0.0.1` (`spark/kernelspec.py`), porque a Web UI do Spark ignora `spark.driver.bindAddress` e usa essa variável. Assim, o RPC do driver, o block manager e a Web UI ficam restritos à loopback. A UI continua ativa, mas sem a ação de matar jobs e stages. Kernelspecs gravados antes dessa mudança não são migrados: o efeito vale para runtimes (re)instalados.

### 7.3 AWS Glue em Docker

- **Imagem:** `notisbook/glue:6.0`, construída a partir de `public.ecr.aws/glue/aws-glue-libs:6.0` (fixada por digest) com `ipykernel` (`runtimes/glue/Dockerfile`). O build exige 15 GiB livres.
- **Container persistente** `notisbook-glue` (`runtimes/docker/service.py`), iniciado com `--network host`, `--cap-drop ALL`, `--security-opt no-new-privileges`, usuário `hadoop` e bind mounts no mesmo caminho do host. Pastas sensíveis do home (`.aws`, `.ssh`, `.gnupg`, `.kube`, `.docker`) são recusadas como montagem.
- **Kernel:** `runtimes/docker/launch.py` executa `docker exec -i` no container e entrega o código de bootstrap e o connection file pelo stdin.
- **Acesso ao backend:** o container alcança o backend por `host.lima.internal` (`notisbook/config.py`), só nas rotas de runtime.
- O CLI `docker` respeita `DOCKER_HOST` e o contexto ativo.

> Observação: os argumentos de submit do kernel Glue (`runtimes/docker/incontainer.py`) não definem `spark.driver.bindAddress`/`host`. O alcance de rede das portas do Spark no container depende da rede da VM Docker. Isso não foi verificado em execução.

### 7.4 DuckDB

- O instalador (`runtimes/duckdb/installer.py`) cria um ambiente `uv` com `duckdb` e `ipykernel`.
- As extensões listadas em `runtimes/duckdb/extensions.json` são baixadas de `extensions.duckdb.org`, conferidas por sha256 (`.gz` e descompactado) e validadas com autoinstall e autoload desligados.
- O bootstrap do kernel (`runtimes/duckdb/hook.py`) cria os secrets S3 e anexa o catálogo `notislake` via Iceberg REST.

## 8. Dados e catálogo

### 8.1 Raiz de dados

`$NOTISBOOK_HOME` ou `~/.notisbook` (`notisbook/config.py`):

| Caminho | Uso |
|---|---|
| `envs/`, `kernels/`, `jars/` | ambientes, kernelspecs e cache de jars |
| `catalog.db` | catálogo SQLite |
| `notebooks/` | raiz padrão dos notebooks |
| `minio/` | binário, dados, logs e credencial do MinIO (0600) |
| `duckdb/extensions` | extensões DuckDB |
| `run/backend.json`, `preferences.json`, `notislake-connection.json` | registro da instância, preferências e conexão S3 manual (0600) |
| `warehouse/`, `spark-warehouse/` | warehouses de segurança |

### 8.2 `catalog.db`

Um único SQLite (`notisbook/catalog/store.py`) com WAL e `busy_timeout`:

- `iceberg_tables` e `iceberg_namespace_properties`: o esquema do Iceberg JdbcCatalog, usado diretamente pelo Spark local (`type=jdbc`, `warehouse=s3a://notislake`).
- `nb_namespaces`, `nb_tables` e `nb_meta`: o registro de tabelas Delta, Parquet e Hudi do `spark_catalog`. `nb_meta.generation` sinaliza às sessões que é preciso reconciliar.

No Spark local, Delta e Hudi usam o `spark_catalog` da sessão (`DeltaCatalog`) e Iceberg usa o catálogo nomeado `iceberg` (`spark/bundles.py`).

### 8.3 Catálogo para runtimes fora do processo

Kernels Docker e DuckDB não acessam o SQLite diretamente. O backend expõe:

- `/iceberg/v1/...` (`notisbook/api/iceberg_rest.py`): catálogo Iceberg REST. O próprio servidor grava o `metadata.json` usando `pyiceberg`, com controle de concorrência no SQLite. `register` e `transactions/commit` são recusados (403), e o purge de `s3a` também.
- `/api/runtime-catalog` (`notisbook/api/runtime_catalog.py`): o registro `nb_*` para o hook do kernel Docker.

### 8.4 Notislake (MinIO local)

- **Binário:** o tarball do MinIO vem com a instalação, nunca é baixado em execução. Ele é conferido contra `notislake/minio_manifest.json` (sha256 do tarball e de cada binário) e instalado em `<home>/minio/bin` (`notislake/binary.py`).
- **Supervisor** (`notislake/supervisor.py`):
  - `flock` garante um único backend por home;
  - reaproveita ou encerra processos órfãos;
  - escolhe portas livres em loopback e inicia `minio server --address 127.0.0.1:<p> --console-address 127.0.0.1:<p>`.
- **Layout:** bucket `notislake` com prefixos `landing/`, `bronze/`, `silver/` e `gold/`, criados via `boto3` (`notislake/bootstrap.py`). O hook do kernel aplica as regras de camada nas escritas.
- **Conexão:** um arquivo de conexão S3 manual válido tem prioridade sobre o MinIO local (`notislake/objectstore.py`).
- **Credenciais S3A:** o `spark-defaults.conf` só contém uma configuração fechada (endpoint inválido `http://127.0.0.1:1` e provider anônimo). A conexão real, com a chave secreta, é injetada por sessão pelo hook (`notislake/sparkconf.py`, `kernels/service.py`). No Docker, o endpoint de loopback é trocado por `host.lima.internal`.

## 9. Jobs em background

`notisbook/jobs.py` mantém um registro **em memória**: até 100 jobs e 10.000 eventos `{phase, line, progress}` por job, nos estados `queued`, `running`, `succeeded` e `failed`.

- O WebSocket `/api/jobs/{id}/events` reenvia o log acumulado e continua ao vivo até o evento `done`.
- Jobs cobrem a instalação e as libs de Spark e DuckDB e a instalação do runtime Docker.
- Uma trava por kernel serializa install, libs e remove. Criar uma sessão sobre um ambiente em mutação retorna 409.
- Os jobs não sobrevivem a um restart do processo.

## 10. Segurança

| Controle | Implementação |
|---|---|
| Bind em loopback | backend em `127.0.0.1` sem opção de configuração; MinIO, driver e Web UI do Spark local também em loopback (seções 7.2 e 8.4) |
| Token da UI | `secrets.token_urlsafe(32)` por execução; aceito como Bearer, cookie ou `?token=`; comparação com `secrets.compare_digest` (`notisbook/security.py`) |
| Host/Origin | `require_trusted_host` aceita só `127.0.0.1:<porta>`/`localhost:<porta>` (proteção contra DNS rebinding); o WebSocket exige token, Origin e Host |
| Credenciais de runtime | tokens por sessão, separados do token da UI, válidos só em `/iceberg` e `/api/runtime-catalog`, que aceitam também o host `host.lima.internal` |
| Shutdown | `/api/lifecycle/shutdown` exige cliente loopback e um token de lifecycle próprio, comparado com `hmac.compare_digest` |
| CSP da SPA | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; object-src 'none'` (`notisbook/static.py`) |
| Saídas no navegador | DOMPurify + Shadow DOM; sem execução de JavaScript de saída (seção 6) |
| Export HTML | sanitizado com `nh3` (`export/html_report.py`), servido com `Content-Security-Policy: sandbox`, `nosniff` e `no-store` |
| Libs do usuário | especificações PEP 508/440 validadas (sem URL, `@`, `;`); `uv` com `--no-config` e allowlist de variáveis `UV_*` (`spark/requirements.py`, `spark/packages.py`) |
| Segredos | credencial do MinIO só no ambiente do subprocesso; arquivos sensíveis em 0600; segredos mascarados no `repr` e no painel de info |

**Observações de escopo** (o que o código configura, não garantias operacionais):

- Os routers `contents`, `export`, `sessions`, `spark`, `duckdb`, `jobs` e `/api/health` exigem o token, mas não aplicam `require_trusted_host`.
- `GET /api/notislake/local/credentials` devolve a credencial do MinIO local ao frontend autenticado, com `Cache-Control: no-store`.

## 11. Resiliência

- **MinIO:** monitorado por thread; reinício com backoff de 1, 2, 4, 8 e 16 s. Após 5 falhas consecutivas entra em `failed`, com retry manual (`POST /api/notislake/retry`). O log é rotacionado ao passar de 10 MB.
- **Hook de catálogo:** sondas s3a e HTTP com timeout curto e circuit breaker de 30 s.
- **S3A:** timeouts de conexão de 5 s e de socket de 60 s, com até 2 tentativas.
- **Catálogo de versões Spark:** consulta o PyPI com cache de 1 h e fallback estático.
- **Instalações:** atômicas por ambiente; falha preserva a versão anterior.
- **Downloads:** jars e extensões verificados por sha256; divergência aborta.
- **Encerramento:** ordenado e com orçamentos de tempo fixos (seção 3.3).

## 12. Sistemas externos

| Destino | Quando |
|---|---|
| PyPI (`NOTISBOOK_PYPI_URL` ou `pypi.org`) e as fontes padrão do `uv` | catálogo de versões e instalação de ambientes e libs |
| Maven Central (`NOTISBOOK_MAVEN_URL` ou `repo1.maven.org`) | jars de bundle e S3A |
| `extensions.duckdb.org` | extensões DuckDB |
| Docker daemon e `public.ecr.aws` | build e execução do runtime Glue |
| MinIO local ou endpoint S3 manual | data lake |
| GitHub Releases | só em `notisbook update` e no `install.sh` |
| Ferramentas do macOS (`java_home`, `osascript`, `sysctl`, Homebrew) | JDK, seletor de pasta, fontes e plataforma |

## 13. Build, distribuição e implantação

**Build** (`scripts/build_release.py`):

1. Compila o frontend (`npm ci` + `npm run build`).
2. Copia `frontend/dist` para `notisbook/_frontend`, que entra no wheel como `artifacts`.
3. Gera wheel, `constraints-<v>.txt` e `SHA256SUMS`, com um gate que exige wheels binárias para `aarch64-apple-darwin`.

**MinIO** (`scripts/build_minio.py`): compila `minio` e `mc` em um container Go para `darwin/arm64`, gera um tarball determinístico e atualiza `minio_manifest.json`.

**Release** (`scripts/release.sh X.Y.Z`): exige a `main` limpa e sincronizada; grava a versão (`pyproject.toml`, `uv.lock`, `package.json`), commita, cria a tag, compila e publica a release no GitHub com wheel, constraints, tarball do MinIO, `SHA256SUMS` e `install.sh`. As notas vêm da seção correspondente do `CHANGELOG.md`. Os modos `--dry-run` e `--local-install` ensaiam sem publicar.

**Instalação** (`install.sh`): baixa os assets, confere `SHA256SUMS`, para a instância em execução, roda `uv tool install` a partir do wheel baixado e copia o tarball do MinIO para `~/.local/share/notisbook/notislake`.

**CI:** o único workflow (`.github/workflows/pages.yml`) publica `site/` no GitHub Pages. Não há CI de testes nem de build do app no repositório. A release é manual e local.

## 14. Diagramas

| Vista | Arquivo |
|---|---|
| Contexto | [`docs/arch/context.mmd`](arch/context.mmd) |
| Containers | [`docs/arch/container.mmd`](arch/container.mmd) |
| Componentes do backend | [`docs/arch/component.mmd`](arch/component.mmd) |
| Implantação local | [`docs/arch/deployment.mmd`](arch/deployment.mmd) |
| Fluxo de dados | [`docs/arch/data-flow.mmd`](arch/data-flow.mmd) |

## 15. Limites desta análise

- Gerado por leitura estática de código, configuração e manifestos. A aplicação não foi executada.
- Latência, throughput e comportamento em produção: `Não identificado no código analisado`.
- A rede efetiva do container Glue (seção 7.3) depende do ambiente Docker e não foi verificada.
- Não há testes automatizados nem CI do app no repositório para corroborar o comportamento descrito.

---

**Autor:** DataEduca Platform

**Versão:** 20261124192705

**Data:** 2026-11-24 19:27:05

**SKILL:** Document
