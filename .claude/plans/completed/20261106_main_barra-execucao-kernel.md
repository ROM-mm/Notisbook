# Barra de execução do kernel acima das células

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-06 23:02:44 -0300
Modificação: 2026-11-06 23:36:40 -0300
Finalização: 2026-11-06 23:36:40 -0300

## Objetivo

Barra fixa (sticky) no topo da área das células com 3 ícones — Run all, Interrupt, Restart kernel — que continua visível ao rolar; o "Run all" sai do header (Topbar). As ações já existem no store do kernel (`state/kernel.ts`), então não há mudança no backend nem no menu Run.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `KernelToolbar` com Run all/Interrupt/Restart + ícone de stop, injetada no `NotebookView` via `NotebookPage`, sticky no topo do scroll | python-engineer | — | 1 | escrita |
| T2 | Remover as duas cópias do "Run all" do `Topbar` e o CSS que ficar órfão | python-engineer | T1 | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Botões assinam o estado ao vivo com `useKernel`, mesmas regras do menu Run | Barra permanente precisa refletir estado em tempo real; menu lê só ao abrir | `Topbar.tsx:90-104`; `RunAllButton` em `Topbar.tsx:145-159` já usa `useKernel` | ler estado uma vez (estado velho na tela) |
| D2 | Barra entra como slot passado pelo `NotebookPage`, igual ao `KernelBanner` | `NotebookView` segue sem acesso ao kernel | `NotebookPage.tsx:19-31`; `NotebookView.tsx:196` | `NotebookView` ler `useKernel` direto (acopla a view ao kernel) |
| D3 | Sticky via CSS no container de scroll do `NotebookView` | Pedido do operador: barra "congelada" ao rolar | `NotebookView.tsx:245-255` | barra fora do scroll (no header) — operador quer acima das células |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Barra com 3 botões acima das células, também com notebook vazio | `grep -n 'toolbar-run-all\|toolbar-interrupt\|toolbar-restart' frontend/src/components/kernel/KernelToolbar.tsx` → 3 testids; slot renderizado em `NotebookView.tsx` antes do empty state/`AddCellBar` | feature |
| T1 | Habilitação igual ao menu Run | `KernelToolbar.tsx` usa `useKernel` com `kernelAlive` (Run all), `hasWork` (Interrupt) e `ready` (Restart) conforme `Topbar.tsx:90-93` | feature |
| T1 | Barra fixa, fundo sólido, acima das células | CSS da barra contém `position: sticky`, `top: 0`, `background` e `z-index` | feature |
| T2 | Header sem "Run all" | `grep -rn 'data-testid="run-all"' frontend/src` → vazio | feature |
| T1 | Barra cola na borda superior do scroll, sem faixa de célula visível acima ao rolar (achado do teste manual) | `.toolbar` em `Kernel.module.css` com `top` que compensa o `padding-top` do `.notebook` (ex.: `top: calc(-1 * var(--space-6))`) ou `.notebook` sem `padding-top` com o respiro movido para dentro de `.cells`/toolbar | bugfix |
| T1 | Regras `ready`/`hasWork` vêm de helpers compartilhados (achado minor do code review) | `grep -n "export function kernelReady\|export function kernelHasWork" frontend/src/components/kernel/KernelStatus.tsx` → 2 linhas; `KernelToolbar.tsx` e `runItems` em `Topbar.tsx` usam os helpers, sem expressão inline de `phase===\"ready\"`/`queue.length` | refactor |
| T1 | Frontend compila | `cd frontend && npm run build` → exit 0 | constraint |

## Arquivos previstos
- `frontend/src/components/kernel/KernelToolbar.tsx` — T1
- `frontend/src/components/kernel/NotebookPage.tsx` — T1
- `frontend/src/components/notebook/NotebookView.tsx` — T1
- `frontend/src/components/notebook/Notebook.module.css` — T1
- `frontend/src/components/kernel/Kernel.module.css` — T1
- `frontend/src/components/shell/icons.tsx` — T1
- `frontend/src/components/kernel/KernelStatus.tsx` — T2
- `frontend/src/components/shell/Topbar.tsx` — T2
- `frontend/src/components/shell/AppShell.module.css` — T2

## Fora de escopo
- Atalhos de teclado e "Restart & run all" na barra — não pedidos.
- **Documentação de produto** — nenhuma.

## Não mexer
- Comportamento do menu Run (`runItems` em `Topbar.tsx`): só a troca das expressões pelos helpers compartilhados é permitida (aprovado pelo operador, ajuste pós-review); itens, ações e regras ficam iguais.
- `frontend/src/state/kernel.ts` e todo o backend.

## Status
- [x] T1  - [x] T2

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1-2 | python-engineer | OK | 48076 | 43676 |
| - | plan-auditor | OK | 25754 | 24654 |
| - | code-review | OK | 54528 | 63167 |
| 1 | python-engineer | OK | 23455 | 29139 |
| 1 | python-engineer | OK | 24671 | 31472 |
| 1 | python-engineer | OK | 25246 | 28961 |
| - | plan-auditor | OK | 39787 | 29809 |
| - | code-review | OK | 53056 | 64724 |
| - | memory-manager | OK | 15848 | 36094 |
<!-- effort-ledger:end -->
