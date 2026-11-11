# Pendências cosméticas — spark-sql-e-duckdb

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-07 23:40:00 -0300
Modificação: 2026-11-07 23:40:00 -0300
Finalização: —

## Objetivo

Nits do code review automático (rodada 1, baseline 0c57835) do plano `spark-sql-e-duckdb`. Fora do gatilho do loop; retomar só por decisão do operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/components/notebook/Cell.tsx:43` — usar `languageFamily(cellLanguage(cell))` em vez de repetir a regra | python-engineer | — | 1 | escrita |
| T2 | `frontend/src/state/notebook.ts:215` — renomear `CELL_LANGUAGES` para `EXPLICIT_LANGUAGES` | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/kernels/service.py:376` — `_build_source(language)` com o mesmo `Literal` de `execute` | python-engineer | — | 1 | escrita |
| T4 | `backend/src/notisbook/kernels/sql_cell.py:155-157` — `ext_dir` só vale na 1ª conexão; guardar em `STATE` ou documentar | python-engineer | — | 1 | escrita |
| T5 | `backend/src/notisbook/kernels/sql_cell.py:1-16` — docstring do módulo ≤ 15 linhas | python-engineer | — | 1 | escrita |
| T6 | `backend/src/notisbook/kernels/service.py:557` — `home` obrigatório no `KernelService` (sem `Settings()` de fallback) e `duckdb_ext_dir` sem default vazio | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1–T6

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Editor usa `languageFamily` | `grep -n 'languageFamily(cellLanguage' frontend/src/components/notebook/Cell.tsx` → 1 ocorrência | refactor |
| T2 | Constante renomeada | `grep -rn CELL_LANGUAGES frontend/src` → sem ocorrência | refactor |
| T3 | Tipo alinhado | `grep -n '_build_source' backend/src/notisbook/kernels/service.py` → assinatura com `Literal` | refactor |
| T4 | Limitação de `ext_dir` tratada | leitura de `_duckdb_connection` em `sql_cell.py`: `ext_dir` em `STATE` ou comentário documentando | refactor |
| T6 | `home` obrigatório | `grep -n 'Settings()' backend/src/notisbook/kernels/service.py` → sem ocorrência | refactor |
| T5 | Docstring enxuta | `sed -n '1,20p' backend/src/notisbook/kernels/sql_cell.py` → docstring ≤ 15 linhas | refactor |

## Arquivos previstos
- `frontend/src/components/notebook/Cell.tsx` — T1
- `frontend/src/state/notebook.ts` — T2
- `backend/src/notisbook/kernels/service.py` — T3, T6
- `backend/src/notisbook/kernels/sql_cell.py` — T4, T5

## Fora de escopo
- Qualquer mudança de comportamento — só cosmético.
- **Documentação de produto** — nenhuma. Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- Comportamento das células Python, Spark SQL e DuckDB SQL.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
