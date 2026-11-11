# Botão ▶ sem sombra e com respiro até o seletor de linguagem

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-11 02:14:21 -0300
Modificação: 2026-11-11 02:21:02 -0300
Finalização: 2026-11-11 02:21:02 -0300

## Objetivo

No cabeçalho da célula, o botão ▶ tem sombra própria (`Notebook.module.css:224`, hover/active `:232-242`) e fica colado no seletor de linguagem porque `.headerLeft` (`:185-188`) não tem `gap`. Entrega: botão sem sombra (e sem o deslocamento que a acompanha) e 8px entre ele e o seletor. O botão Render do markdown compartilha `.runBtn` e muda junto, de propósito.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Remover sombra/deslocamento de `.runBtn` e adicionar `gap` em `.headerLeft` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `.runBtn` e seus estados sem `box-shadow` nem `transform` | `awk '/^\.runBtn/,/^}/' frontend/src/components/notebook/Notebook.module.css \| grep -cE 'box-shadow\|transform'` = 0 | feature |
| T1 | 8px entre botão e seletor | `awk '/^\.headerLeft \{/,/^}/' frontend/src/components/notebook/Notebook.module.css \| grep -c 'gap: var(--space-2)'` = 1 | feature |
| T1 | Build passa | `cd frontend && npm run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/src/components/notebook/Notebook.module.css` — T1

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- `global.css`, `Menu.module.css`, `tokens.css`, `.addBtn` e a sombra do cartão da célula (`.cell`/`.cellActive`).

## Status
- [x] T1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 42916 | 31238 |
| 1 | python-engineer | OK | 16559 | 26532 |
| 1 | code-review | aprovar | 26146 | 57279 |
| 1 | plan-auditor | CONFORME | 26564 | 19828 |
<!-- effort-ledger:end -->
