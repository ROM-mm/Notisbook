# Pendências cosméticas — tabela do DataFrame

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-10
Modificação: 2026-11-10
Finalização: —

## Objetivo

Resolver os nits do code review da tabela do DataFrame, sem mudar comportamento.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| N1 | `frontend/src/components/outputs/HtmlOutput.tsx:24` — hover das linhas some no tema claro (`--color-bg-hover` = `--color-bg-subtle`); usar realce próprio (ex.: amarelo com `--on-fill`) | python-engineer | — | 1 | escrita |
| N2 | `frontend/src/components/outputs/HtmlOutput.tsx:22` — borda de 2px em todas as linhas do `thead` (MultiIndex do pandas); aplicar só em `thead tr:last-child th` | python-engineer | — | 1 | escrita |
| N3 | `backend/src/notisbook/kernels/sql_cell.py:64` — cor `.null` `#8a8f98` com contraste ~3:1 sobre a zebra (backend) | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N1..N3

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| N2 | borda grossa só na última linha do cabeçalho | `grep -n "tr:last-child" frontend/src/components/outputs/HtmlOutput.tsx` → presente | fix |

## Arquivos previstos
- `frontend/src/components/outputs/HtmlOutput.tsx`
- `backend/src/notisbook/kernels/sql_cell.py`

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/api/**`, `frontend/src/state/**`, `frontend/src/ws/**`.

## Status
- [ ] N1  - [ ] N2  - [ ] N3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
