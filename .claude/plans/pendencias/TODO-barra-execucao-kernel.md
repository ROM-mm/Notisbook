# Pendências cosméticas — barra de execução do kernel

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 23:07:49 -0300
Modificação: 2026-11-06 23:13:46 -0300
Finalização: —

## Objetivo

Nits do code review do plano barra-execucao-kernel: quebra de docstring e semântica ARIA da toolbar.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/components/notebook/NotebookView.tsx:4` — linha da docstring passa de ~80 colunas; quebrar após "slot `toolbar`." | python-engineer | — | 1 | escrita |
| T3 | `frontend/src/components/kernel/Kernel.module.css:202` — `height: 44px` repete `.panelHeader` (`AppShell.module.css:80`); criar token `--panel-header-height` e usar nos dois | python-engineer | — | 1 | escrita |
| T2 | `frontend/src/components/kernel/KernelToolbar.tsx:17` — `role="toolbar"` sem roving tabindex; trocar por `role="group"` (mantendo `aria-label`) ou implementar setas ←/→ | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Docstring ≤ 80 colunas | `awk 'NR<=10 && length>80' frontend/src/components/notebook/NotebookView.tsx` → vazio | refactor |
| T2 | Sem `role="toolbar"` sem roving tabindex | `grep -n 'role="toolbar"' frontend/src/components/kernel/KernelToolbar.tsx` → vazio, ou handler de ArrowLeft/ArrowRight presente no arquivo | refactor |
| T3 | Altura vem de token compartilhado | `grep -rn "panel-header-height" frontend/src` → definição + uso em `Kernel.module.css` e `AppShell.module.css` | refactor |

## Arquivos previstos
- `frontend/src/components/notebook/NotebookView.tsx` — T1
- `frontend/src/components/kernel/KernelToolbar.tsx` — T2
- `frontend/src/components/kernel/Kernel.module.css` — T3
- `frontend/src/components/shell/AppShell.module.css` — T3

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/state/kernel.ts` e o backend.

## Status
- [ ] T1  - [ ] T2  - [ ] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
