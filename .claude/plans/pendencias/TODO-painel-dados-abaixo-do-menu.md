# Pendências cosméticas — painel-dados-abaixo-do-menu

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-05 13:30:57 -0300
Modificação: 2026-11-05 13:30:57 -0300

## Objetivo

Registrar os nits do code review do plano `20261105_main_painel-dados-abaixo-do-menu.md`. Eles não bloqueiam o commit e ficam para ser retomados depois, se o operador quiser.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|---|---|---|---|---|---|
| N1 | `frontend/src/components/shell/AppShell.tsx:10`: o comentário ainda diz que o DataPanel é "por ora só visual", o que deixou de valer desde 5e69c25 | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N1

## Critérios de aceite
| id | critério | verificação | tipo |
|---|---|---|---|
| N1 | Comentário sem "só visual" | `grep -n "só visual" frontend/src/components/shell/AppShell.tsx` → vazio | refactor |

## Arquivos previstos
- `frontend/src/components/shell/AppShell.tsx` — N1

## Fora de escopo
- O comentário de `frontend/src/App.tsx:3` (ordem antiga do layout) foi observado no review, mas não é achado deste changeset.
- **Documentação de produto** — nenhuma.

## Não mexer
- Qualquer regra de CSS ou estrutura JSX do AppShell.

## Status
- [ ] N1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
