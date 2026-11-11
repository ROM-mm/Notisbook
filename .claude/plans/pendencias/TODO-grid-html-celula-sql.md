# Pendências cosméticas — grade HTML da célula SQL

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 17:20:03 -0300
Modificação: 2026-11-06 17:21:37 -0300
Finalização: —

## Objetivo

Nits do code review do plano `grid-html-celula-sql` (rodada 1), fora do gatilho do loop; retomáveis pelo operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `sql_cell.py:33` — cor do `null` fixa `#8a8f98`; usar `var(--color-text-subtle, #8a8f98)` | python-engineer | — | 1 | escrita |
| T2 | `sql_cell.py:53`/`:61` — `class=""` vazio em `th`/`td` não numéricos; omitir o atributo | python-engineer | — | 1 | escrita |
| T3 | `sql_cell.py:70`/`:77` — fallback `text/plain` não normaliza `\r`/`\t` em valores nem quebras em nomes de coluna | python-engineer | — | 1 | escrita |
| T4 | `sql_cell.py:92` — comentário inline de 4 linhas; enxugar para 3 | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `null` usa token do tema | `grep -n "color-text-subtle" backend/src/notisbook/kernels/sql_cell.py` → presente | refactor |
| T2 | sem `class=""` no HTML gerado | `grep -n 'class=\"\"' backend/src/notisbook/kernels/sql_cell.py` → sem saída | refactor |
| T3 | `\r`/`\t` normalizados no plain | leitura de `plain_table` em `sql_cell.py` → valores e nomes normalizados | bugfix |
| T4 | comentário de `sql_cell.py:92` com ≤ 3 linhas | leitura de `sql_cell.py:92` | refactor |

## Arquivos previstos
- `backend/src/notisbook/kernels/sql_cell.py` — T1, T2, T3, T4

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/**`, `protocol.py`.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
