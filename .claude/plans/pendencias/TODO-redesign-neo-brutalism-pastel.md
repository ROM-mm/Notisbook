# Pendências cosméticas — redesign Neo-Brutalism pastel

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-10
Modificação: 2026-11-10
Finalização: —

## Objetivo

Resolver os nits do code review (rodada 1) do redesign visual, sem mudar comportamento.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| N1 | `frontend/src/styles/global.css:51` — `a:hover` sem `color: var(--on-fill)` (ilegível no escuro, latente) | python-engineer | — | 1 | escrita |
| N2 | `frontend/src/styles/global.css:19` — `border-radius:0 !important` sem espaço; documentar que exceções exigem revisar a regra | python-engineer | — | 1 | escrita |
| N3 | `frontend/src/components/notebook/CellHeader.tsx:181` — `data-cell-type` colide com o do wrapper (`Cell.tsx:108`); renomear para `data-cell-lang` | python-engineer | — | 1 | escrita |
| N4 | `frontend/src/components/notebook/Notebook.module.css:369` — comentário desatualizado | python-engineer | — | 1 | escrita |
| N5 | `frontend/src/components/spark/Spark.module.css:396` — comentário cita regra `.neo .btn:hover` removida | python-engineer | — | 1 | escrita |
| N6 | `frontend/src/components/notebook/Notebook.module.css:314` — input de título sem estado de foco visível | python-engineer | — | 1 | escrita |
| N7 | `frontend/src/styles/tokens.css:64` — `--color-border` igual a `--color-border-strong`; tabelas do `HtmlOutput.tsx` ficam pesadas | python-engineer | — | 1 | escrita |
| N8 | `frontend/src/components/shell/Menu.module.css:89` — hover/foco do `.item` muda para bold e pode alargar o menu | python-engineer | — | 1 | escrita |
| N9 | `frontend/src/styles/tokens.css:88` — comentário ainda diz "Marca (Spark Spiral)"; logo agora é N-Block | python-engineer | — | 1 | escrita |
| N10 | `frontend/src/components/notebook/Notebook.module.css:6-7` — comentário diz que a paleta de sintaxe acompanha `html_report.py`; com D4=b ela diverge de propósito | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N1..N10

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| N1 | link legível no hover | `grep -n "a:hover" -A3 frontend/src/styles/global.css` → contém `--on-fill` | fix |
| N3 | atributo sem colisão | `grep -n "data-cell-lang" frontend/src/components/notebook/CellHeader.tsx` → presente | fix |
| N6 | foco visível no título | regra `:focus` no input de título em `Notebook.module.css` | fix |

## Arquivos previstos
- `frontend/src/styles/global.css`
- `frontend/src/styles/tokens.css`
- `frontend/src/components/notebook/CellHeader.tsx`
- `frontend/src/components/notebook/Notebook.module.css`
- `frontend/src/components/spark/Spark.module.css`
- `frontend/src/components/shell/Menu.module.css`

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/api/**`, `frontend/src/state/**`, `frontend/src/ws/**`, `backend/**`.

## Status
- [ ] N1  - [ ] N2  - [ ] N3  - [ ] N4  - [ ] N5  - [ ] N6  - [ ] N7  - [ ] N8  - [ ] N9  - [ ] N10

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
