# Visual em cartão — painel Variables

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 13:45:40 -0300
Modificação: 2026-11-10 13:57:19 -0300
Finalização: 2026-11-10 13:57:19 -0300

## Objetivo

Aplicar ao painel Variables o padrão de cartão dos painéis Data/Notebooks, conforme o mockup aprovado variables-v1: cabeçalho branco com linha de 2px, "after [N]" e "stale" como pílulas contornadas (stale em amarelo); corpo pontilhado com a árvore e os estados (vazio, erro, carregando) dentro de um cartão (2px, raio 14px, sombra creme 4px) que acompanha o conteúdo; glifos de tipo como selos contornados; linha em hover/foco como pílula com borda e mini-sombra; estados vazios com contorno tracejado. Só visual — textos, leitura das variáveis, expansão, paginação ("Show N more…"), teclado e redimensionamento ficam iguais.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Cabeçalho com linha 2px; "after [N]" e "stale" como pílulas contornadas | python-engineer | — | 1 | escrita |
| T2 | Corpo pontilhado; árvore e estados num cartão que acompanha o conteúdo (no .tsx só wrapper/className) | python-engineer | T1 | 1 | escrita |
| T3 | Selos de tipo contornados; linha em hover/foco como pílula sem deslocar layout; vazios tracejados | python-engineer | T2 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Cartão acompanha o conteúdo | mockup aprovado; pontilhado aparece embaixo, como em Data | sem evidência — aprovação do operador no mockup | ocupar o painel inteiro |
| D2 | Pílula no hover e no foco | o painel não tem seleção persistente | `VariablesPanel.tsx` sem estado de seleção (levantamento read-only) | pílula só no foco |
| D3 | Selos de tipo contornados, sem cor | leitura de tipo mantendo o padrão monocromático | sem evidência — aprovação do operador no mockup | glifo cinza como hoje |
| D4 | Alça de redimensionar continua "line" | painel encostado no notebook, sem vão entre cartões | `VariablesPanel.tsx:282-290` | variante "gap" |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Cabeçalho com linha 2px | `grep -A10 "^\.header {" frontend/src/components/variables/VariablesPanel.module.css \| grep "2px solid var(--cell-border)"` encontra | feature |
| T1 | "after [N]" em pílula contornada | `grep -A8 "^\.badge {" frontend/src/components/variables/VariablesPanel.module.css \| grep -E "999px\|var\(--cell-border\)"` encontra as duas | feature |
| T2 | Corpo pontilhado | `grep "radial-gradient" frontend/src/components/variables/VariablesPanel.module.css` encontra `var(--canvas-dot)` | feature |
| T2 | Cartão 2px com sombra 4px | `grep -A10 "^\.card {" frontend/src/components/variables/VariablesPanel.module.css \| grep -E "2px solid var\(--cell-border\)\|4px 4px 0 var\(--cell-shadow\)"` encontra as duas | feature |
| T3 | Selo de tipo contornado | `grep -A8 "^\.glyph {" frontend/src/components/variables/VariablesPanel.module.css \| grep "var(--cell-border)"` encontra | feature |
| T3 | Linha em hover/foco com mini-sombra | `grep -A6 "^\.row:hover\|^\.row:focus-visible" frontend/src/components/variables/VariablesPanel.module.css \| grep "var(--btn-shadow)"` encontra | feature |
| T2 | .tsx sem mudança de textos ou handlers (diff ignora reindentação: `-w` acrescentado após a implementação, o wrapper reindenta linhas sem alterá-las) | `git diff -w <baseline> -- frontend/src/components/variables/VariablesPanel.tsx \| grep -E "^[+-].*(onClick\|onKeyDown\|onDrag\|title=\|aria-label\|>[A-Z][a-z])"` sem saída | constraint |
| T3 | Nome/tipo longo não vaza para fora do cartão | `grep -A14 "^\.row {" frontend/src/components/variables/VariablesPanel.module.css \| grep "overflow: hidden"` encontra | bugfix |
| T1 | Build do frontend passa | `npm --prefix frontend run build` exit 0 | constraint |
| T1 | Store e ResizeHandle intocados | `git diff <baseline> -- frontend/src/state frontend/src/components/shell/ResizeHandle.tsx` vazio | constraint |

## Arquivos previstos
- `frontend/src/components/variables/VariablesPanel.module.css` — T1, T2, T3
- `frontend/src/components/variables/VariablesPanel.tsx` — T2

## Fora de escopo
- Busca, ordenação, seleção persistente e ações por linha (o painel não tem hoje).
- Nits pendentes das rodadas anteriores e a promoção do `.neo` para a `.btn` global.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/state/**`, `frontend/src/components/shell/ResizeHandle.tsx`, `frontend/src/components/shell/AppShell.tsx`, `frontend/src/styles/global.css`.
- Textos, teclado (setas, Enter, Space) e o comportamento de expandir/carregar mais.

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 34772 | 36480 |
| 1 | python-engineer | OK | 12041 | 26726 |
<!-- effort-ledger:end -->
