# Visual em cartão — topbar, abas, banner e barra de execução

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 12:20:58 -0300
Modificação: 2026-11-10 12:46:37 -0300
Finalização: 2026-11-10 12:46:37 -0300

## Objetivo

Levar ao topo da aplicação o padrão de cartão já validado (células, Settings, diálogos, painéis, menus), conforme o mockup aprovado topbar-abas-v1: banner com linha de 2px; faixa de abas com linha de 2px e aba ativa como cartão branco (borda 2px, cantos superiores arredondados) encaixado na topbar, com leve sombra creme à direita, inativas planas; topbar branca com linha de 2px, item de menu aberto com borda e mini-sombra, status do kernel em pílula contornada, seletor de ambiente como botão com borda e mini-sombra, Variables ligado igual ao item ativo do rail, RAM/CPU/Disk com contorno tracejado leve; barra Run all/Interrupt/Restart como cartão (2px, raio 12px, sombra creme 4px) com Run all destacado. Ampliação aprovada pelo operador após o commit 00aed07 (menu de assunto, opção 1): os botões "+ Code"/"+ Markdown" entre as células também passam ao estilo novo (pílula com borda 1.5px, fundo de superfície e mini-sombra). Só visual — textos, itens de menu, atalhos, regras de habilitação e o comportamento de abrir/fechar/trocar abas ficam iguais.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Banner com linha 2px; faixa de abas e aba ativa em cartão encaixado | python-engineer | — | 1 | escrita |
| T2 | Topbar branca com linha 2px; menu aberto com borda/mini-sombra; Variables ligado como o rail; RAM/CPU/Disk com contorno tracejado | python-engineer | — | 1 | escrita |
| T3 | Status do kernel em pílula contornada; seletor de ambiente como botão com borda e mini-sombra | python-engineer | — | 1 | escrita |
| T4 | Barra Run all/Interrupt/Restart como cartão, Run all destacado (no .tsx só className) | python-engineer | — | 1 | escrita |
| T5 | Botões "+ Code"/"+ Markdown" (`.addBtn`) no estilo novo, só CSS (ampliação) | python-engineer | — | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3 → T4
- Wave 2 (serial, escrita, ampliação): T5

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Aba ativa como cartão encaixado na topbar, sombra creme à direita | mantém a leitura de "pasta" da aba atual | `AppShell.module.css:163-169` (aba ativa já sobrepõe a linha) | aba plana |
| D2 | RAM/CPU/Disk com contorno tracejado | diferencia informação de botão | sem evidência — aprovação do operador no mockup | só texto |
| D3 | Banner muda só na linha de 2px | a marca já tem identidade própria | memória identidade-visual-grid-n-por-tema | redesenhar o banner |
| D4 | Barra de execução como cartão separado | combina com as células | sem evidência — aprovação do operador no mockup | faixa com linha |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Banner com linha 2px | `grep -A14 "^\.banner {" frontend/src/components/shell/Banner.module.css \| grep "2px solid var(--cell-border)"` encontra a linha | feature |
| T1 | Aba ativa como cartão 2px com sombra creme | `grep -A10 "^\.tab\[data-active\]" frontend/src/components/shell/AppShell.module.css \| grep -E "2px solid var\(--cell-border\)\|var\(--cell-shadow\)"` encontra as duas | feature |
| T2 | Topbar com linha 2px | `grep -A14 "^\.topbar {" frontend/src/components/shell/AppShell.module.css \| grep "2px solid var(--cell-border)"` encontra | feature |
| T2 | Variables ligado com borda e mini-sombra, sem azul | `grep -A6 '^\.topToggle\[aria-pressed="true"\]' frontend/src/components/shell/AppShell.module.css` mostra `var(--btn-shadow)` e não mostra `--color-accent-subtle` | feature |
| T2 | Menu aberto com borda e mini-sombra | `grep -A8 "^\.barTrigger\[data-open\]\|^\.barTrigger:hover" frontend/src/components/shell/Menu.module.css \| grep "var(--btn-shadow)"` encontra | feature |
| T3 | Status em pílula | `grep -A12 "^\.status {" frontend/src/components/kernel/Kernel.module.css \| grep "999px"` encontra | feature |
| T3 | Seletor como botão com mini-sombra | `grep -A14 "^\.selector {" frontend/src/components/kernel/Kernel.module.css \| grep "var(--btn-shadow)"` encontra | feature |
| T4 | Barra de execução como cartão | `grep -A16 "^\.toolbar {" frontend/src/components/kernel/Kernel.module.css \| grep -E "2px solid var\(--cell-border\)\|4px 4px 0 var\(--cell-shadow\)"` encontra as duas | feature |
| T4 | KernelToolbar.tsx só muda className | `git diff <baseline> -- frontend/src/components/kernel/KernelToolbar.tsx \| grep -E "^[+-].*(onClick\|disabled\|title=\|aria-label)"` sem saída | constraint |
| T1 | Sombra da aba ativa não pinta sobre a linha da faixa | `grep -A10 "^\.tab\[data-active\] {" frontend/src/components/shell/AppShell.module.css` não contém `box-shadow: 3px 0 0`; `grep -A8 "^\.tab\[data-active\]::after" frontend/src/components/shell/AppShell.module.css \| grep -E "bottom: 2px\|var\(--cell-shadow\)"` encontra as duas | bugfix |
| T4 | Barra de execução colada ao topo e alinhada ao cabeçalho do painel (44px, sem offset) | `grep -A16 "^\.toolbar {" frontend/src/components/kernel/Kernel.module.css \| grep -E "top: 0\|height: 44px"` encontra as duas e não há `margin-top: 4px` | bugfix |
| T5 | `.addBtn` com borda 1.5px e mini-sombra | `grep -A16 "^\.addBtn {" frontend/src/components/notebook/Notebook.module.css \| grep -E "1.5px solid var\(--cell-border\)\|var\(--btn-shadow\)"` encontra as duas | feature |
| T5 | AddCellBar.tsx intocado | `git diff <baseline> -- frontend/src/components/notebook/AddCellBar.tsx` vazio | constraint |
| T1 | Build do frontend passa | `npm --prefix frontend run build` exit 0 | constraint |
| T1 | global.css, Topbar.tsx e TabBar.tsx intocados | `git diff <baseline> -- frontend/src/styles/global.css frontend/src/components/shell/Topbar.tsx frontend/src/components/shell/TabBar.tsx` vazio | constraint |

## Arquivos previstos
- `frontend/src/components/shell/Banner.module.css` — T1
- `frontend/src/components/shell/AppShell.module.css` — T1, T2
- `frontend/src/components/shell/Menu.module.css` — T2
- `frontend/src/components/kernel/Kernel.module.css` — T3, T4
- `frontend/src/components/kernel/KernelToolbar.tsx` — T4
- `frontend/src/components/notebook/Notebook.module.css` — T5

## Fora de escopo
- Promover `.neo` para a `.btn` global e remover o escopo — rodada própria depois que todas as telas estiverem migradas.
- KernelBanner e o botão "Close tab" do NotebookView.
- Nits pendentes das rodadas anteriores.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/styles/global.css`, `frontend/src/components/shell/Topbar.tsx`, `frontend/src/components/shell/TabBar.tsx`, `frontend/src/components/kernel/KernelSelector.tsx`, `frontend/src/components/kernel/KernelStatus.tsx`, `frontend/src/components/shell/SystemResources.tsx`, `frontend/src/components/shell/Banner.tsx`, `frontend/src/state/**`.
- Textos, itens de menu, atalhos, regras de habilitação e comportamento das abas.
- Dropdown dos menus (`.list`/`.item` em Menu.module.css), já padronizado.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 49405 | 41493 |
| 1 | python-engineer | OK | 20976 | 28763 |
| 2 | python-engineer | OK | 16481 | 26765 |
<!-- effort-ledger:end -->
