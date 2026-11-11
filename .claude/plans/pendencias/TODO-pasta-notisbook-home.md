# Pendências cosméticas — pasta base ~/.notisbook

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

## Objetivo

Nits do code review do plano `pasta-notisbook-home`, fora do gatilho do loop.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `backend/src/notisbook/config.py:8` — `config` depende de `spark.kernelspec` só por `ENVS_DIR`; mover `ENVS_DIR` para módulo leve (ex.: `spark/layout.py`) quando `kernelspec.py` puder ser tocado | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/config.py:26` — `ensure_home` recebe `Settings` inteiro mas usa só `home`; trocar para `ensure_home(home: Path)` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `config.py` não importa `spark.kernelspec` | `grep -n 'kernelspec' backend/src/notisbook/config.py` → nenhuma ocorrência | refactor |
| T2 | `ensure_home` recebe `Path` | `grep -n 'def ensure_home(home: Path)' backend/src/notisbook/config.py` → presente | refactor |

## Arquivos previstos
- `backend/src/notisbook/config.py` — T1, T2
- `backend/src/notisbook/spark/kernelspec.py` — T1
- `backend/src/notisbook/__main__.py` — T2

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Comportamento da raiz `NOTISBOOK_HOME`/`~/.notisbook` e do preparo de pastas no start.

## Status
- [ ] T1  - [ ] T2

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
