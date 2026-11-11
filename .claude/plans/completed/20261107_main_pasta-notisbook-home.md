# Pasta base ~/.notisbook para ambientes e warehouse

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-07 00:38:00 -0300
Modificação: 2026-11-07 01:02:25 -0300
Finalização: 2026-11-07 01:02:25 -0300

## Objetivo

Os dados do Notisbook passam a viver em `~/.notisbook` (override por `NOTISBOOK_HOME`): ambientes Spark em `~/.notisbook/envs` e warehouse Iceberg em `~/.notisbook/warehouse/iceberg`, no lugar de `~/spark-notebooks` e `~/spark-labs` (ambos sob `SPARK_LABS_HOME`, com dois padrões divergentes). A pasta base e as subpastas são criadas no início da aplicação se não existirem; falha ao criar aborta o start com caminho e motivo. Ambientes já instalados não são migrados por código: o operador reinstala pela tela de Spark e apaga `~/spark-notebooks/envs` à mão (mover exigiria reescrever shebangs/`activate` absolutos do venv).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Raiz única `NOTISBOOK_HOME` ou `~/.notisbook` em `Settings`, usada pelo instalador; `SPARK_LABS_HOME` sai | python-engineer | — | 1 | escrita |
| T2 | Warehouse Iceberg do `spark-defaults.conf` derivado da raiz única (`<raiz>/warehouse/iceberg`); `default_labs_home` sai | python-engineer | T1 | 1 | escrita |
| T3 | Criação de `<raiz>`, `<raiz>/envs` e `<raiz>/warehouse` no start, idempotente; falha aborta com caminho e motivo | python-engineer | T1 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Override por `NOTISBOOK_HOME`; `SPARK_LABS_HOME` deixa de ser lida | `SPARK_LABS_HOME` já tinha dois padrões (`~/spark-notebooks` e `~/spark-labs`) e é usada pelo `start-jupyter.sh` legado | `backend/src/notisbook/config.py:17-20`, `backend/src/notisbook/spark/bundles.py:149-151` | manter `SPARK_LABS_HOME` como fallback — descartado: mantém a ambiguidade |
| D2 | Ambientes atuais: reinstalar pela UI, sem código de migração | só 2 ambientes; mover exige reescrever caminhos absolutos em `kernel.json`, `spark-defaults.conf`, `activate` e 17 shebangs | diagnóstico do knowledge-engineer nesta sessão | migração automática; aceitar raiz legada no `discover` |
| D3 | Pastas criadas no start (antes de servir), não sob demanda | pedido do operador; falha de permissão aparece no start, não na 1ª instalação | sem evidência — preferência do operador | criar só ao instalar (comportamento atual) |
| D4 | Kernelspecs continuam em `jupyter_data_dir()/kernels` | mudar exige `JUPYTER_DATA_DIR` e altera a descoberta de kernels do `jupyter_client` | `backend/src/notisbook/spark/kernelspec.py:58-59` | kernelspecs sob `~/.notisbook` |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Raiz padrão `~/.notisbook` | `cd backend && env -u NOTISBOOK_HOME -u SPARK_LABS_HOME uv run python -c "from pathlib import Path; from notisbook.config import Settings; print(Settings().home == Path.home()/'.notisbook')"` → `True` | feature |
| T1 | `NOTISBOOK_HOME` sobrepõe a raiz | `cd backend && NOTISBOOK_HOME=/tmp/nb-x uv run python -c "from notisbook.config import Settings; print(Settings().home)"` → `/tmp/nb-x` | feature |
| T1 | Nenhuma referência às raízes antigas no código | `git grep -n -e SPARK_LABS_HOME -e spark-notebooks -e spark-labs -- backend/src start.sh` → nenhuma ocorrência | constraint |
| T1 | Instalador recebe a raiz única e cria ambientes em `<raiz>/envs` | leitura: `backend/src/notisbook/app.py` passa `settings.home` ao `SparkInstaller`; `kernelspec.ENVS_DIR` segue `"envs"` | feature |
| T2 | Warehouse Iceberg sob a raiz única | `cd backend && uv run python -c "from pathlib import Path; from notisbook.spark.bundles import MATRIX, render_spark_defaults; b=next(iter(MATRIX.values())); print('/h/warehouse/iceberg' in render_spark_defaults(b, Path('/j'), Path('/h')))"` → `True`; `git grep -n default_labs_home -- backend/src` → nenhuma ocorrência | feature |
| T3 | Start cria raiz, `envs` e `warehouse` se não existem, e é idempotente | com `NOTISBOOK_HOME=<scratch>/h` inexistente, chamar a função de preparo do start duas vezes → as 3 pastas existem, sem erro na 2ª chamada | feature |
| T3 | Falha ao criar aborta o start com caminho e motivo | `NOTISBOOK_HOME=<arquivo-regular> uv run notisbook --no-browser --port 8799` → exit ≠ 0 e stderr com o caminho e o motivo; nenhum servidor sobe | feature |
| T3 | Erro de preparo mostra o caminho que de fato falhou (raiz, `envs` ou `warehouse`) — achado minor do review, rodada 1 | com `NOTISBOOK_HOME=<scratch>/h3` e um ARQUIVO regular em `<scratch>/h3/envs`, `uv run notisbook --no-browser --port 8799` → exit 1 e stderr contém `<scratch>/h3/envs` | bugfix |
| T2 | Nome da pasta do warehouse vem de uma constante única usada pelo start e pelo `spark-defaults.conf` — achado minor do review, rodada 1 | `git grep -n "'warehouse'\|\"warehouse\"" -- backend/src` → exatamente 1 ocorrência (a definição da constante) | refactor |
| T3 | Backend importa e o app sobe | `NOTISBOOK_HOME=<scratch>/h2 uv run notisbook --no-browser --port 8799` responde `/api/health` e cria `<scratch>/h2/envs` e `<scratch>/h2/warehouse` | constraint |

## Arquivos previstos
- `backend/src/notisbook/config.py` — T1, T3
- `backend/src/notisbook/app.py` — T1
- `backend/src/notisbook/spark/bundles.py` — T2
- `backend/src/notisbook/spark/installer.py` — T2
- `backend/src/notisbook/__main__.py` — T3

## Fora de escopo
- Migração dos ambientes em `~/spark-notebooks/envs` e da tabela `vendas` em `~/spark-labs` — feita à mão pelo operador (D2).
- `~/spark-notebooks/.venv-jupyter` e `start-jupyter.sh` — legado fora do Notisbook.
- **Documentação de produto** — nenhuma (o repo não tem README nem `docs/`).

## Não mexer
- Local dos kernelspecs (`jupyter_data_dir()/kernels`) e a regra de descoberta/remoção por pai `<raiz>/envs` em `backend/src/notisbook/spark/kernelspec.py` (D4).
- Raiz dos notebooks (`~/notebooks`, `--root`) e as flags da CLI.
- Frontend.

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 84407 | 43558 |
| 1 | python-engineer | OK | 34871 | 37075 |
| 1 | code-review | ajustes necessários | 61672 | 60648 |
| 1 | plan-auditor | CONFORME | 29057 | 24453 |
| 1 | python-engineer | OK | 148133 | 33710 |
| 1 | code-review | aprovar | 47510 | 58894 |
| 1 | plan-auditor | CONFORME | 28076 | 23834 |
<!-- effort-ledger:end -->
