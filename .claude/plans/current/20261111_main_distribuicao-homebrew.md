# Distribuição via Homebrew

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-11 01:00:47 -0300
Modificação: 2026-11-11 01:00:47 -0300
Finalização: —

## Objetivo

Depois de `brew install <usuario>/tap/notisbook`, digitar `notisbook` no terminal tem que abrir o app funcionando como pelo `./start.sh` hoje. Para isso, o pacote Python precisa levar o frontend já compilado, encontrar sozinho o JDK do Homebrew e gerar um sdist limpo, com licença Apache-2.0. A Formula Ruby, o repositório do tap e a publicação da release ficam com o operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Frontend compilado dentro do pacote e localizado em runtime | python-engineer | — | 1 | escrita |
| T2 | Achar o JDK pelo `JAVA_HOME` e pelo keg do Homebrew | python-engineer | — | 1 | escrita |
| T3 | Licença, `--version` e sdist só com o necessário | python-engineer | — | 1 | escrita |
| T4 | Script de release: build do frontend, sdist + wheel e sha256 | python-engineer | T1,T3 | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3
- Wave 2 (serial, escrita): T4

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Repositório público, licença Apache-2.0 | instalação sem token | sem evidência — escolha do operador | privado com token e estratégia de download própria no tap |
| D2 | A fórmula baixa o sdist anexado à release | o tarball automático do GitHub levaria `.claude/`, `.idea/` e as notas | `git ls-files` (114 arquivos em `.claude/`) | `.gitattributes` com `export-ignore` |
| D3 | Frontend em `notisbook/_frontend` no pacote; ordem de busca: `NOTISBOOK_FRONTEND_DIST`, depois `frontend/dist` do repositório (se existir), depois o pacote | o desenvolvimento continua usando o build vivo; o pacote instalado usa o embutido | `backend/src/notisbook/config.py:36-41`, `backend/src/notisbook/static.py:20-28` | Node na fórmula, com wrapper exportando a variável |
| D4 | Ordem de busca do JDK: `JAVA_HOME` com a versão certa, depois `/usr/libexec/java_home -v`, depois `$(brew --prefix)/opt/openjdk@<major>` | o `openjdk@17` do Homebrew é keg-only e o `java_home` não o enxerga | `backend/src/notisbook/spark/prereqs.py:115-143`, `backend/src/notisbook/spark/installer.py:407` | só aviso nos `caveats` |
| D5 | `.idea/`, `Notisbook.iml` e `notisbook-sqlite-catalog.md` continuam no git, fora do pacote | decisão do operador | sem evidência — preferência do operador | tirar do rastreamento |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | O wheel instalado acha o frontend embutido | em um venv limpo com o wheel: `python -c "from notisbook.config import default_frontend_dist as f; p=f(); print(p, (p/'index.html').exists())"` → caminho dentro de `site-packages/notisbook/_frontend` e `True` | feature |
| T1 | O desenvolvimento continua servindo `frontend/dist` do repositório | `uv run --project backend python -c "from notisbook.config import default_frontend_dist as f; print(f())"` → `<repo>/frontend/dist` | constraint |
| T1 | A cópia embutida do frontend não é versionada | `git check-ignore backend/src/notisbook/_frontend/index.html` → caminho impresso (exit 0) | constraint |
| T2 | Com `JAVA_HOME` apontando para um JDK 17 fora do `java_home`, o instalador usa esse JDK | chamada a `notisbook.spark.prereqs:jdk_for_spark` para Spark 3.5 com esse `JAVA_HOME` → devolve o caminho dele | feature |
| T2 | Sem `JAVA_HOME`, o resultado é o mesmo de hoje | `env -u JAVA_HOME` + `jdk_for_spark` para Spark 3.5 → igual a `/usr/libexec/java_home -v 17` | constraint |
| T2 | Busca no keg do Homebrew presente | `grep -n 'openjdk@' backend/src/notisbook/spark/prereqs.py` → ao menos 1 linha | feature |
| T3 | Licença Apache-2.0 declarada | `head -1 LICENSE` → `Apache License`; `grep -n 'Apache-2.0' backend/pyproject.toml` → 1 linha | feature |
| T3 | `notisbook --version` imprime a versão | `uv run --project backend notisbook --version` → `0.1.0` | feature |
| T3 | O sdist não leva nada indevido | `tar -tzf backend/dist/notisbook-0.1.0.tar.gz \| grep -E '\.claude\|\.venv\|\.idea\|\.iml\|sqlite-catalog\|_cache'` → vazio | constraint |
| T4 | Um comando gera sdist e wheel, ambos com o frontend | `uv run --project backend python scripts/build_release.py`; depois `tar -tzf` e `unzip -l` → contêm `notisbook/_frontend/index.html` | feature |
| T4 | O script imprime o sha256 do sdist | valor impresso = `shasum -a 256 backend/dist/notisbook-0.1.0.tar.gz` | feature |
| T4 | O wheel gerado instala e o comando roda | venv limpo + `uv pip install backend/dist/*.whl` + `notisbook --help` → exit 0 | feature |

## Arquivos previstos
- `backend/src/notisbook/config.py` — T1
- `backend/pyproject.toml` — T1, T3
- `.gitignore` — T1
- `backend/.gitignore` — T1
- `backend/src/notisbook/spark/prereqs.py` — T2
- `backend/src/notisbook/spark/installer.py` — T2
- `LICENSE` — T3
- `backend/LICENSE` — T3
- `backend/src/notisbook/__init__.py` — T3
- `backend/src/notisbook/__main__.py` — T3
- `scripts/build_release.py` — T4

## Fora de escopo
- Formula Ruby, repositório `homebrew-tap`, release e push no GitHub — ficam com o operador (política de linguagens e controle do remote).
- Workflow de CI para gerar o build a cada tag — pode vir numa rodada futura.
- Publicação no PyPI e envio ao homebrew-core.
- Unificar as versões do `pyproject.toml` e do `package.json`.
- **Documentação de produto** — o README de instalação não existe e continua não existindo; reportado ao operador no fim, não criado aqui.

## Não mexer
- `start.sh` e o fluxo de desenvolvimento
- `~/.notisbook` / `NOTISBOOK_HOME`, porta 8765, token na URL, escuta só em `127.0.0.1`
- Instalação do PySpark por versão em tempo de execução (`spark/installer.py`, exceto a escolha do JDK)
- `.claude/`, `.idea/`, `Notisbook.iml`, `notisbook-sqlite-catalog.md`
- `frontend/src/**`

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
