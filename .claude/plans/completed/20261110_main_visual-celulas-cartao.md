# Visual das células — cartão neo-brutalista suave

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 10:35:02 -0300
Modificação: 2026-11-10 10:57:11 -0300
Finalização: 2026-11-10 10:57:11 -0300

## Objetivo

Trocar o visual das células do notebook para o mockup v2 aprovado pelo operador: cartão com borda de 2px em preto suavizado, cantos de 16px e sombra sólida deslocada (`6px 6px 0`) em cinza creme; cabeçalho branco, sem cor por tipo de célula, separado do corpo por uma linha; código num campo branco simples (sem moldura estilo janela macOS); fundo pontilhado na área do notebook. Mudança só de CSS: conteúdo e comportamento do cabeçalho (Run, número/título, menus) e a saída das células permanecem iguais. Uma coluna, sem grid bento.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Variáveis de cor de borda, sombra e pontilhado do fundo, temas claro e escuro | python-engineer | — | 1 | escrita |
| T2 | Cartão, cabeçalho branco com linha inferior e corpo da célula no novo estilo; célula em edição só troca a cor da borda | python-engineer | T1 | 1 | escrita |
| T3 | Fundo pontilhado na área do notebook | python-engineer | T1 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Uma coluna, sem grid bento | notebook é lido e executado em ordem linear | sem evidência — validação do operador no mockup v2 | grid de 2 colunas (mockup v1) |
| D2 | Cores em variáveis de tema com variante escura (borda cinza clara, sombra quase preta, pontos discretos) | sombra creme e borda escura sumiriam no fundo escuro | `Notebook.module.css:29-58` já separa paleta clara/escura | valores fixos só do tema claro |
| D3 | Saída das células intocada | operador: "a saída tem que ser o mesmo que está hoje" | sem evidência — preferência do operador | restilizar a grade de saída |
| D4 | Célula ativa ganha sombra dura mais escura (`--cell-shadow-active`); em edição, só a borda vira a cor de destaque e a sombra ativa é herdada (edição implica ativa) | seleção visível no modo comando, onde atalhos destrutivos (D D) agem; accent reservado à edição | code review rodada 1 — `.cellActive` repetia a sombra base | sombra creme na edição (padrão inicial); sombra na cor de destaque (mockup v1) |
| D5 | Cabeçalho sem cor por tipo de célula | operador pediu visual minimalista, tudo branco | sem evidência — preferência do operador | faixa pastel por tipo (mockup v2) |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `--cell-border`, `--cell-shadow` e `--canvas-dot` definidas nos temas claro e escuro | `grep -c -- "--cell-shadow:" frontend/src/styles/tokens.css` ≥ 2; idem `--cell-border:` e `--canvas-dot:` | feature |
| T2 | `.cell` com borda 2px, raio 16px e sombra `6px 6px 0` usando as variáveis de T1 | `grep -A10 "^\.cell {" frontend/src/components/notebook/Notebook.module.css` mostra `2px solid var(--cell-border)`, `16px` e `6px 6px 0 var(--cell-shadow)` | feature |
| T2 | Cabeçalho com fundo branco e linha inferior | `grep -A10 "^\.cellHeader" frontend/src/components/notebook/Notebook.module.css` mostra `background: var(--color-bg)` e `border-bottom` | feature |
| T2 | Célula em edição troca só a cor da borda | `grep -A4 "^\.cellEditing" frontend/src/components/notebook/Notebook.module.css` mostra `border-color: var(--color-accent)` (sombra creme herdada de `.cell`) | feature |
| T3 | `.notebook` com fundo pontilhado | `grep "radial-gradient" frontend/src/components/notebook/Notebook.module.css` encontra a regra com `var(--canvas-dot)` | feature |
| T2 | Célula ativa (modo comando) tem destaque próprio, distinto da inativa e do accent de edição | `grep -A4 "^\.cellActive" frontend/src/components/notebook/Notebook.module.css` mostra `box-shadow` diferente de `var(--cell-shadow)` e sem `--color-accent` | bugfix |
| T2 | `.cellEditing` declara só `border-color` (sem `box-shadow` redundante) | `grep -A4 "^\.cellEditing" frontend/src/components/notebook/Notebook.module.css` não contém `box-shadow` | refactor |
| T1 | Build do frontend continua passando | `npm --prefix frontend run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/src/styles/tokens.css` — T1
- `frontend/src/components/notebook/Notebook.module.css` — T2, T3

## Fora de escopo
- Export HTML (`backend/src/notisbook/export/html_report.py`) — segue com o visual atual nesta rodada.
- Topbar, abas, painel lateral e barra sticky de Run all.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/components/outputs/**` e o renderer da grade (`backend/src/notisbook/kernels/sql_cell.py`).
- `frontend/src/components/notebook/CellHeader.tsx`, `Cell.tsx`, `CodeEditor.tsx` — markup e comportamento.
- Paleta `--syntax-*` em `Notebook.module.css`.

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 32661 | 38274 |
| 1 | python-engineer | OK | 21197 | 28187 |
<!-- effort-ledger:end -->
