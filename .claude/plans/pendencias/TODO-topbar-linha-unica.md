# Pendências cosméticas — topbar em linha única

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

## Objetivo

Nits do code review da topbar em linha única (plano `topbar-linha-unica`), fora do gatilho do loop.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/components/shell/AppShell.module.css:226` — tirar o `margin-top` da base `.menubar` e aplicá-lo só no caso de duas linhas, eliminando o override `.topbarSingle .menubar` | python-engineer | — | 1 | escrita |
| T3 | `frontend/src/components/shell/AppShell.module.css:234` — `min-width: 0` inócuo em item `flex: none` e `.topbarSingle .menubar` em dois blocos; juntar num só (com T1) | python-engineer | — | 1 | escrita |
| T4 | `frontend/src/components/shell/AppShell.module.css:242,247,253` — layout amarrado a `data-testid` do KernelSelector; em plano que libere `components/kernel/*`, expor `className`/`align="end"`; por ora prefixar a linha 253 com `.topbarSingle` | python-engineer | — | 1 | escrita |
| T2 | `frontend/src/components/shell/Topbar.tsx:175` — sem `<h1>` com notebook aberto; adicionar `<h1>` visualmente oculto (sr-only) com o nome do notebook | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Sem override de margin-top da menubar | `grep -n 'topbarSingle .menubar' frontend/src/components/shell/AppShell.module.css` → nenhuma ocorrência | refactor |
| T3 | Um único bloco `.topbarSingle .menubar`, sem `min-width: 0` inócuo | `grep -c '^.topbarSingle .menubar' frontend/src/components/shell/AppShell.module.css` → 1 | refactor |
| T4 | Regra da lista do seletor escopada a `.topbarSingle` | `grep -n 'topbarSingle .topActions \[data-testid="kernel-selector-list"\]' frontend/src/components/shell/AppShell.module.css` → presente | refactor |
| T2 | Página do notebook tem h1 acessível oculto | `grep -n '<h1' frontend/src/components/shell/Topbar.tsx` → presente no ramo com `entry`, com classe sr-only | feature |

## Arquivos previstos
- `frontend/src/components/shell/AppShell.module.css` — T1
- `frontend/src/components/shell/Topbar.tsx` — T2

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Layout visual da topbar em linha única.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
