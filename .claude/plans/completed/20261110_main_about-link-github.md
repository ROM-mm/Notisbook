# Link do GitHub no diálogo About

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-10 23:42:49 -0300
Modificação: 2026-11-10 23:50:12 -0300
Finalização: 2026-11-10 23:50:12 -0300

## Objetivo

No diálogo About, logo abaixo do nome "Romerito Morais", exibir o link do GitHub do autor (`https://github.com/ROM-mm`, texto `github.com/ROM-mm`), abrindo em nova aba com `target="_blank"` e `rel="noopener noreferrer"`, no estilo de link do app (Neo-Brutalism pastel). Uso do dado pessoal confirmado pelo operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Adicionar o link do GitHub abaixo do nome no AboutDialog | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Build sem erro | `cd frontend && npm run build` → exit 0 | constraint |
| T1 | Typecheck limpo | `cd frontend && npm run typecheck` → exit 0 | constraint |
| T1 | Link presente | `grep -n "github.com/ROM-mm" frontend/src/components/shell/AboutDialog.tsx` → presente | feature |
| T1 | Abertura segura | `grep -n 'rel="noopener noreferrer"' frontend/src/components/shell/AboutDialog.tsx` → presente | constraint |
| T1 | (review r1) Foco inicial do diálogo continua no botão Close | `AboutDialog.tsx` foca o botão Close ao abrir (ref + `.focus()` após `showModal()` ou `autoFocus`) | fix |
| T1 | Nada fora do diálogo mudou | `git diff --stat <baseline> -- frontend/src ':(exclude)frontend/src/components/shell/AboutDialog.tsx' ':(exclude)frontend/src/components/shell/AppShell.module.css' ':(exclude)frontend/src/styles/dialog.module.css'` → vazio | constraint |

## Arquivos previstos
- `frontend/src/components/shell/AboutDialog.tsx` — T1
- CSS do diálogo, só se precisar de estilo (`frontend/src/components/shell/AppShell.module.css` ou `frontend/src/styles/dialog.module.css`) — T1

## Fora de escopo
- Outras telas e as pendências cosméticas de `.claude/plans/pendencias/`.
- **Documentação de produto** — nenhuma.

## Não mexer
- Demais textos do About e o restante da interface; `backend/**`.

## Status
- [x] T1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer (T1) | OK | 19443 | 28937 |
| 1 | python-engineer (T1 review r1) | OK | 14578 | 27432 |
<!-- effort-ledger:end -->
