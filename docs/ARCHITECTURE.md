# Arquitetura do Notisbook

Descrição da estrutura observada no código (`backend/src/notisbook/`, `frontend/src/`, manifestos e scripts). Afirmações sobre ambiente de execução real que o código não comprova estão marcadas como inferência ou `Não identificado no código analisado`.

Diagramas: [contexto](arch/context.mmd) · [containers](arch/container.mmd) · [componentes](arch/component.mmd) · [implantação](arch/deployment.mmd) · [fluxo de dados](arch/data-flow.mmd).

## 1. Visão geral

O Notisbook é uma aplicação local de usuário único:

| parte | tecnologia | evidência |
|---|---|---|
| Servidor | Python ≥3.12, FastAPI, uvicorn | `backend/pyproject.toml`, `backend/src/notisbook/app.py` |
| Interface | React 19, TypeScript, Vite, zustand, CodeMirror 6 | `frontend/package.json` |
| Execução de código | kernels Jupyter via `jupyter_client` (AsyncKernelManager) | `backend/src/notisbook/kernels/service.py` |
| Ambientes Spark | venvs criados com `uv`, PySpark do PyPI, jars do Maven Central | `backend/src/notisbook/spark/installer.py`, `spark/bundles.py` |
| Catálogo | SQLite `catalog.db` (WAL) | `backend/src/notisbook/catalog/store.py` |

## 2. Processos em execução

- **Servidor**: um processo uvicorn com bind fixo em `127.0.0.1` (porta padrão 8765, `--port` muda), access log desligado (`__main__.py:62-67`, `config.py:11-12`). No start: cria `~/.notisbook` (`envs/`, `warehouse/`), cria/migra o `catalog.db`, resolve a pasta dos notebooks (`--root` > preferência salva > `~/notebooks`) e abre o navegador (`__main__.py:45-65`).
- **Kernels**: um processo por sessão de notebook, iniciado pelo `AsyncKernelManager`. O kernelspec de cada ambiente executa `<env>/bin/python -m ipykernel_launcher` com `JAVA_HOME`, `PYSPARK_PYTHON`, `PYSPARK_DRIVER_PYTHON` e `SPARK_CONF_DIR` explícitos; o ambiente herdado é limpo de `SPARK_HOME`, `PYTHONPATH`, `PYSPARK_*` e `SPARK_CONF_DIR` (`spark/kernelspec.py:71-90`, `kernels/service.py:54-61`).
- **JVM do Spark**: inferência — sobe dentro do processo do kernel quando o notebook cria uma SparkSession.
- **Navegador**: carrega a SPA servida pelo próprio servidor.

O `lifespan` limpa connection files órfãos e lixo de ambientes removidos na subida, e encerra jobs e kernels no desligamento (`app.py:20-30`).

## 3. Backend

| módulo | responsabilidade |
|---|---|
| `__main__.py` | CLI (`--version`, `--port`, `--root`, `--no-browser`) e bootstrap |
| `app.py` | fábrica FastAPI, ordem dos routers, header `X-Notisbook: 1` |
| `config.py` | configuração imutável: host, porta, home, dist do frontend, URL do PyPI |
| `security.py` | token, trusted host, guarda de WebSocket |
| `static.py` | arquivos estáticos e fallback da SPA com CSP |
| `api/` | rotas REST e WebSocket |
| `notebooks/store.py` | leitura/escrita de `.ipynb` em sandbox, escrita atômica |
| `kernels/` | sessões, protocolo WS v1, módulos ocultos injetados no kernel (`_notisbook_display`, `_notisbook_catalog`), introspecção de variáveis |
| `catalog/` | esquema do `catalog.db`, registro `nb_*`, leitura/escrita do formato Iceberg JDBC, schemas |
| `spark/` | instalador de ambientes, matriz de bundles, kernelspec, catálogo de versões, libs, pré-requisitos |
| `files/` | navegação por caminho absoluto, seletor de pasta nativo (macOS) |
| `export/` | export `.py` e `.html` |
| `jobs.py` | jobs em memória com log reproduzível |
| `preferences.py`, `fs_safety.py` | preferências e proteções de exclusão |

O servidor não expõe OpenAPI (`docs_url`, `redoc_url` e `openapi_url` são `None`, `app.py:34`); a especificação em [api/swagger.yaml](api/swagger.yaml) é mantida à parte.

## 4. Frontend

- SPA com rotas `/`, `/tree/<dir>`, `/notebooks/<path>` e `/settings` (`state/router.ts`).
- Estado em stores zustand: workspace, notebook (um por aba), kernel (fila de execução, uma célula por vez), catalog, files, notebookTree, variables, layout, systemResources, theme.
- Clientes REST em `api/` e WebSocket com reconexão em `ws/`.
- O token fica só em memória; é retirado da URL com `history.replaceState` (`api/auth.ts`).
- Fontes empacotadas no bundle, porque a CSP não permite CDN.
- O servidor procura o build nesta ordem: `NOTISBOOK_FRONTEND_DIST` → `frontend/dist` do repositório → `notisbook/_frontend` embutido no pacote (`config.py:36-44`). Sem `index.html`, responde 503.

## 5. Ambientes Spark

- Cada ambiente fica em `~/.notisbook/envs/spark-<versão>-<hash>/`, instalado em fases (`prereqs`, `python`, `venv`, `install`, `bundle`, `validate`, `kernelspec`, `cleanup`) por `uv python install 3.12`, `uv venv` e `uv pip install pyspark==<v> ipykernel duckdb==2.0.0 [delta-spark]` (`spark/installer.py:60,358-365`).
- Os jars de Delta, Iceberg, Hudi e o driver `sqlite-jdbc` vêm de uma matriz estática com sha256 fixo, baixados do Maven Central na instalação; o kernel não faz download (`spark/bundles.py`).
- A validação roda um teste de fumaça do Spark com timeout de 300 s (`spark/installer.py:485-517`).
- O JDK segue a linha do Spark: 3.x → 17; demais → 21, senão 17. Busca: `$JAVA_HOME` (se o major servir) → `/usr/libexec/java_home -v N` → keg `openjdk@N` do Homebrew (`spark/prereqs.py:132-203`).
- Install, remoção e gestão de libs do mesmo ambiente compartilham um lock (`spark/installer.py:172-195`). As libs são instaladas só do PyPI, com especificações validadas (`spark/requirements.py`).

## 6. Dados e persistência

| local | conteúdo |
|---|---|
| `~/.notisbook` (ou `NOTISBOOK_HOME`) | `envs/`, `warehouse/spark`, `warehouse/iceberg`, `catalog.db`, `preferences.json` (0600), `duckdb/extensions` |
| `~/notebooks` (padrão, trocável) | notebooks `.ipynb` |
| `jupyter_data_dir()/kernels` | kernelspecs dos ambientes |
| `jupyter_runtime_dir()/notisbook` | connection files dos kernels (0700) |

Kernelspecs e connection files ficam **fora** de `~/.notisbook`, nos diretórios padrão do Jupyter (`spark/kernelspec.py:51-60`, `kernels/service.py:525`).

O `catalog.db` tem três escritores (`catalog/store.py`, `kernels/catalog_hook.py`, `spark/bundles.py:172-176`):

1. o backend, ao criar e excluir schemas;
2. o módulo oculto de cada kernel, que registra tabelas Delta/Parquet em `nb_tables`;
3. o `JdbcCatalog` do Iceberg (catálogo `iceberg`), via `jdbc:sqlite`.

O Spark usa catálogo em memória (`spark.sql.catalogImplementation=in-memory`), sem metastore Hive; o hook do kernel re-hidrata o catálogo da sessão a partir do `catalog.db`.

## 7. Integrações externas

| destino | uso | controle |
|---|---|---|
| PyPI JSON (`NOTISBOOK_PYPI_URL`) | lista de versões do PySpark | cache 1 h, timeout 5 s, fallback estático |
| Índice PyPI via `uv` | PySpark, ipykernel, duckdb, libs do usuário | `--no-config --default-index`, variáveis `UV_*` filtradas |
| Maven Central (`NOTISBOOK_MAVEN_URL`) | jars de lakehouse | só http(s), sha256 verificado, timeout 60 s |
| `uv` | CPython 3.12 e pacotes | hosts usados pelo `uv`: `Não identificado no código analisado` |
| `osascript` (macOS) | seletor de pasta nativo | lock, timeout 300 s |

## 8. API e protocolo

- REST sob `/api` (contents, export, fs, notebooks-root, sessions, variables, catalog, spark, jobs, system) — ver [api/swagger.yaml](api/swagger.yaml).
- WebSocket `/api/sessions/{id}/channel`, protocolo próprio v1 orientado a célula: cliente envia `execute`, `interrupt`, `restart`; servidor envia `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error`. Saída limitada a 1 MB por célula (`kernels/protocol.py`, `kernels/service.py`).
- WebSocket `/api/jobs/{id}/events` transmite o log de instalação/libs.
- Requests de escrita carregam `X-Notisbook-Root-Generation`; se a pasta dos notebooks mudou, a resposta é 409 `root_changed`.

## 9. Segurança

Controles configurados no código (não comprovam garantia operacional):

- Bind fixo em loopback; token `secrets.token_urlsafe(32)` por inicialização, aceito por `Authorization: Bearer`, cookie `notisbook_token` (HttpOnly, SameSite=Strict) ou `?token=`; comparação em tempo constante (`security.py`).
- Verificação de Host (`127.0.0.1:<porta>`/`localhost:<porta>`) nas rotas de sistema, fs, notebooks-root, catálogo e variáveis; o WebSocket verifica Origin e Host. As demais rotas REST dependem do token e do cookie SameSite. Não há CORS.
- CSP na SPA (`default-src 'self'`, `frame-ancestors 'none'`) e no HTML exportado (`default-src 'none'`).
- Sanitização: `nh3` no export HTML; DOMPurify e Shadow DOM no frontend.
- Exclusões restritas por allowlist: pastas dentro da home ou `/Volumes`, nunca home, raiz, pasta de dados ou ancestrais; schemas com etag; tabelas MANAGED só sob o warehouse.
- Escritas atômicas (arquivo temporário + `os.replace`) para notebooks, preferências e configurações de ambiente.
- Subprocessos sempre por argv, sem shell.

## 10. Distribuição

- Pacote Python `notisbook` 0.1.0 (hatchling), com o frontend compilado embutido em `notisbook/_frontend` (`backend/pyproject.toml:28-35`).
- `scripts/build_release.py` compila o frontend, gera sdist e wheel e imprime o sha256 do sdist.
- Instalação para usuários pelo tap Homebrew `rom-mm/tap` (ver [README](../README.md#instalação)); a fórmula fica no repositório `ROM-mm/homebrew-tap`, fora deste.
- Não há CI/CD, Dockerfile nem testes versionados neste repositório.

## 11. Resiliência

- Jobs de instalação e de libs ficam em memória; o log é reenviado a quem reconecta ao WebSocket. Um restart do servidor encerra os jobs.
- O frontend reconecta o WebSocket com backoff.
- SQLite com `BEGIN IMMEDIATE` e `busy_timeout` (5 s no backend, 10 s no JDBC).
- Métricas, tracing ou alertas: `Não identificado no código analisado`.

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
