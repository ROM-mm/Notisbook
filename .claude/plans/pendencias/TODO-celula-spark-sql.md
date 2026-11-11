# Pendências (nits) — célula Spark SQL

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 15:42:37 -0300
Modificação: 2026-11-06 15:45:07 -0300
Finalização: —

## Objetivo

Nits do code review r1 do plano `20261106_main_celula-spark-sql`, guardados para uma rodada futura. Não bloqueiam o commit.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/components/notebook/CellHeader.tsx:137` — ariaLabel do seletor anuncia a linguagem atual | python-engineer | — | 1 | escrita |
| T2 | `frontend/src/state/kernel.ts:240` — regra "python vai sem o campo" em um lugar só (duplicada com `ws/session.ts:80`) | python-engineer | — | 1 | escrita |
| T3 | `frontend/src/ws/protocol.ts:4` / `ws/session.ts:4` — `CellLanguage` definido em `ws/` ou `api/`, sem `ws/` importar de `state/` | python-engineer | — | 1 | escrita |
| T4 | `frontend/src/components/notebook/CodeEditor.tsx:4` — um só mecanismo de recriação da view (key ou efeito) e comentário coerente | python-engineer | — | 1 | escrita |
| T5 | `frontend/src/components/notebook/CellHeader.tsx:115` — seletor SQL só com kernelspec de linguagem `python` | python-engineer | — | 1 | escrita |
| T6 | `frontend/src/components/notebook/Notebook.module.css:366` — cor do gatilho do seletor também em `:hover` e `[data-open]` (empate de especificidade com `.iconTrigger`) | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1–T5

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | ariaLabel com a linguagem | `grep -n 'Linguagem da célula:' frontend/src/components/notebook/CellHeader.tsx` → match | refactor |
| T2 | Regra em um lugar | `grep -n '=== "sql" ? language : undefined' frontend/src/state/kernel.ts` → sem match | refactor |
| T3 | ws/ não importa state/ | `grep -n 'state/notebook' frontend/src/ws/` → sem match | refactor |
| T4 | Um mecanismo de recriação | `grep -n 'languageOf(cell)}' frontend/src/components/notebook/Cell.tsx` sem a key composta, ou efeito sem `language` nas deps — um dos dois | refactor |
| T5 | Seletor condicionado ao kernel Python | `grep -n 'language' frontend/src/components/notebook/CellHeader.tsx` mostra a condição pelo kernelspec | feature |
| T6 | Cor no hover/aberto | `grep -n 'aria-haspopup="menu"\]:hover' frontend/src/components/notebook/Notebook.module.css` → match | refactor |

## Arquivos previstos
- `frontend/src/components/notebook/CellHeader.tsx` — T1, T5
- `frontend/src/state/kernel.ts` — T2
- `frontend/src/ws/protocol.ts` — T3
- `frontend/src/ws/session.ts` — T2, T3
- `frontend/src/components/notebook/CodeEditor.tsx` — T4
- `frontend/src/components/notebook/Cell.tsx` — T4
- `frontend/src/components/notebook/Notebook.module.css` — T6

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Backend (`backend/src/notisbook/`)

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T5 NÃO resolvido: retirado do plano (sem sinal de kernel SQL no front) — ver TODO-correcoes-pendencias-alta.md
