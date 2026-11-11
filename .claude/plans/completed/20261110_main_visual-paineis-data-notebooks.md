# Visual em cartão — painéis Data e Notebooks, rail e menus

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 11:26:56 -0300
Modificação: 2026-11-10 11:58:41 -0300
Finalização: 2026-11-10 11:58:41 -0300

## Objetivo

Aplicar ao painel lateral o padrão de cartão já validado (células, Settings, diálogos), conforme o mockup aprovado paineis-data-notebooks-v1: rail com item ativo em botão branco com borda e mini-sombra (sem fundo azul); cabeçalho do painel com linha de 2px e painel com borda direita de 2px; CATALOG, FILES e a árvore de Notebooks como cartões (2px, raio 14px, sombra creme 4px) sobre fundo pontilhado, sem a caixa cinza das árvores; linha selecionada como pílula com borda e mini-sombra (azul só para o notebook da aba ativa); menus (contexto e topbar, que compartilham Menu.module.css) com borda 2px e sombra grafite; divisória CATALOG/FILES vira o espaço entre os cartões. Ampliação de escopo aprovada pelo operador após o commit 7f0e397 (menu de assunto, opção 1): os botões da tela inicial "No notebook open" (New notebook / Open Notebooks panel) também passam ao estilo novo, só os botões. Só visual — textos, itens de menu, clique/expandir/renomear/apagar e o redimensionamento ficam iguais.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Rail (ativo com borda e mini-sombra), cabeçalho do painel com linha 2px, borda direita do painel, escopo `.neo` no painel | python-engineer | — | 1 | escrita |
| T2 | Aba Data: fundo pontilhado, CATALOG/FILES em cartões, sem caixa cinza, seleção em pílula, divisória no espaço entre cartões (variante visual do ResizeHandle, sem mudar o arrasto) | python-engineer | T1 | 1 | escrita |
| T3 | Aba Notebooks: fundo pontilhado, barra da pasta + árvore num cartão, seleção em pílula, notebook ativo em azul | python-engineer | T1 | 1 | escrita |
| T4 | Menus (Menu.module.css): borda 2px, raio 12px, sombra sólida grafite, hover neutro | python-engineer | — | 1 | escrita |
| T5 | Botões da tela inicial no estilo novo via escopo `.neo` em `.homeActions` (ampliação) | python-engineer | — | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3 → T4
- Wave 2 (serial, escrita, ampliação): T5

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Menus de contexto e da topbar mudam juntos | compartilham a mesma folha; aprovado pelo operador | `ContextMenu.tsx` reusa `Menu.module.css` (levantamento read-only) | folhas separadas; adiar menus |
| D2 | Divisória CATALOG/FILES vira o espaço entre cartões via variante do ResizeHandle | estilo do handle é inline; lógica de arrasto e reset por duplo clique intactas | `ResizeHandle.tsx:32-42` | manter linha de 1px |
| D3 | Cartões do painel com sombra 4px e raio 14px | painel tem 288px; 6px pesa | sem evidência — mockup aprovado | 6px/16px como as células |
| D4 | Notebooks mantém duas barras | aprovado pelo operador | sem evidência — preferência do operador | juntar numa barra |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Item ativo do rail com borda e mini-sombra, sem fundo azul | `grep -A6 '^\.railItem\[aria-pressed="true"\]' frontend/src/components/shell/AppShell.module.css` mostra `var(--cell-border)` e `var(--btn-shadow)`, sem `--color-accent-subtle` | feature |
| T1 | Cabeçalho do painel com linha 2px | `grep -A10 "^\.panelHeader" frontend/src/components/shell/AppShell.module.css` mostra `border-bottom: 2px solid var(--cell-border)` | feature |
| T2 | Seções do Data como cartões | `grep -A14 "^\.section {" frontend/src/components/data/DataPanel.module.css | grep -E "2px solid var\(--cell-border\)|4px 4px 0 var\(--cell-shadow\)"` mostra as duas linhas (janela trocada de -A10 por filtro exato na auditoria rodada 1) | feature |
| T2 | Corpo do Data com fundo pontilhado | `grep "radial-gradient" frontend/src/components/data/DataPanel.module.css` encontra `var(--canvas-dot)` | feature |
| T2 | Arrasto do ResizeHandle inalterado | `git diff <baseline> -- frontend/src/components/shell/ResizeHandle.tsx` não altera linhas de handlers `onPointer*`/`onDoubleClick` | constraint |
| T3 | Árvore de Notebooks em cartão sobre pontilhado | `grep -c "var(--cell-border)\|radial-gradient" frontend/src/components/files/FileBrowser.module.css` ≥ 2 | feature |
| T4 | Menus com borda 2px e sombra grafite | `grep -A14 "^\.list {" frontend/src/components/shell/Menu.module.css | grep -E "2px solid var\(--cell-border\)|var\(--dialog-shadow\)"` mostra as duas linhas (janela trocada de -A10 por filtro exato na auditoria rodada 1) | feature |
| T4 | Hover/foco de item de menu visível nos dois temas (sem `--color-bg-muted`, que empata com a superfície no escuro) | `grep -n -A3 "^\.item:hover\|^\.item:focus-visible" frontend/src/components/shell/Menu.module.css` não contém `--color-bg-muted` | bugfix |
| T1 | Sem linha dupla entre painel e alça vertical | `grep -A12 "^\.panel {" frontend/src/components/shell/AppShell.module.css` não contém `border-right` | bugfix |
| T2 | Arrasto CATALOG/FILES acompanha o cursor sem mudar a lógica: o contêiner medido não tem padding e a alça "gap" ocupa ≤ 1px de layout | `git diff <baseline> -- frontend/src/components/data/DataPanel.tsx` só contém a linha `variant="gap"`; `grep -A8 "^\.panel {" frontend/src/components/data/DataPanel.module.css` não contém `padding` | bugfix |
| T5 | `.homeActions` compõe o escopo `.neo` | `grep -A4 "^\.homeActions {" frontend/src/components/shell/AppShell.module.css` mostra `composes: neo from` | feature |
| T5 | Markup da tela inicial intocado | `git diff <baseline> -- frontend/src/App.tsx` vazio | constraint |
| T1 | Build do frontend passa | `npm --prefix frontend run build` exit 0 | constraint |
| T1 | global.css intocado | `git diff <baseline> -- frontend/src/styles/global.css` vazio | constraint |

## Arquivos previstos
- `frontend/src/components/shell/AppShell.module.css` — T1, T5
- `frontend/src/components/shell/SidePanel.tsx` — T1
- `frontend/src/components/data/DataPanel.module.css` — T2
- `frontend/src/components/data/DataPanel.tsx` — T2
- `frontend/src/components/data/CatalogSection.tsx` — T2
- `frontend/src/components/data/FilesSection.tsx` — T2
- `frontend/src/components/data/FileTree.tsx` — T2
- `frontend/src/components/shell/ResizeHandle.tsx` — T2
- `frontend/src/components/files/FileBrowser.module.css` — T3
- `frontend/src/components/files/FileBrowser.tsx` — T3
- `frontend/src/components/files/NotebookTree.tsx` — T3
- `frontend/src/components/shell/Menu.module.css` — T4

## Fora de escopo
- Topbar, abas e o resto da home (título/texto) — próximas rodadas (só os menus da topbar mudam, por D1, e os botões da home, por T5).
- Nits pendentes das rodadas anteriores (tokens repetidos, raios literais).
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/styles/global.css`, `backend/**`, `frontend/src/state/**`, `frontend/src/components/shell/ContextMenu.tsx`.
- Textos, itens de menu e lógica de clique/expandir/renomear/apagar/redimensionar nos `.tsx` (só `className`/import de estilo e a variante visual do ResizeHandle).
- `frontend/src/components/notebook/**`, `frontend/src/components/spark/**`, `frontend/src/components/settings/**`, `frontend/src/styles/dialog.module.css`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 87475 | 61122 |
| 1 | python-engineer | OK | 51552 | 37412 |
| 1 | python-engineer | OK | 27969 | 30372 |
| 2 | python-engineer | OK | 13721 | 25471 |
<!-- effort-ledger:end -->
