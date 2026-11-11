# Redesign visual Neo-Brutalism pastel (app inteiro)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 21:34:46 -0300
Modificação: 2026-11-10 22:51:56 -0300
Finalização: 2026-11-10 22:51:56 -0300

## Objetivo

Aplicar a linguagem visual validada pelo operador (mockup P1.1, claro × escuro) em TODO o frontend: telas, painéis, diálogos, menus, botões, células, saídas, ícones, logo e favicons. **Somente mudança visual** — nenhum comportamento, API, estado, fluxo ou texto de interface muda.

Referência obrigatória para os engineers (valores exatos, layout e estados): `.claude/plans/mockups/neo-brutalism-pastel/` — `styles.css` (tokens `:root` e `.dark`), `board.html`, `final-P1.1.png`, `sections/P01..P13.png`, `logos/`. Onde o mockup e este plano divergirem, vale este plano (`## Fora de escopo` / `## Decisões`).

Linguagem: borda sólida (claro `#000`, escuro `#CFC9BC`) 2px em elementos densos e 3px em molduras; `border-radius: 0` em tudo; sombra sólida sem blur (claro `#000`, escuro `#1B1A20`); fundo do app creme `#FEFEEE` / grafite `#2B2A31` com pontilhado; superfícies `#FFFFFF`/`#35343C` e `#F6F5DF`/`#3E3D46`; pastéis claro (amarelo `#FDE68A`, azul `#BFDBFE`, pêssego `#FED7AA`, lavanda `#DDD6FE`, rosa `#FBCFE8`, menta `#BBF7D0`, água `#A5F3FC`, coral `#FECACA`) e versões suavizadas no escuro (`#E6D48E`, `#A9C2E0`, `#E2C09C`, `#C3BCE0`, `#DFB8CD`, `#A9D3B6`, `#9ACFD5`, `#DFAEAE`), texto sobre pastel `#000` / `#2A2930`; texto claro `#000`, escuro `#E8E4DA`. Topbar amarela; rail e cabeçalhos dos painéis laterais na cor de fundo do app; aba ativa = superfície (branca); faixa pastel por tipo de célula (Python azul, Spark SQL pêssego, DuckDB lavanda, Markdown rosa); seleção de linha amarela + barra 3px; botão primário amarelo, destrutivo coral; hover/pressed com deslocamento; foco = outline 3px reto.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Base visual: tokens claro/escuro, fontes (Space Grotesk, Public Sans, Archivo Black), botões/inputs/scrollbar únicos, raio 0 global | python-engineer | — | 1 | escrita |
| T2 | Moldura: topbar, banner, rail, abas, cabeçalhos de painel, medidor RAM/CPU/Disk, menus, tela de status | python-engineer | T1 | 2 | escrita |
| T3 | Notebook: cartão de célula com faixa por tipo, seleção/edição, add-cell, barra de execução, status/seletor/aviso do kernel | python-engineer | T1 | 2 | escrita |
| T4 | Painéis Notebooks, Data e Variables (cartões, linhas, estados vazios, breadcrumb) | python-engineer | T1 | 2 | escrita |
| T5 | Settings / Spark environments e seus diálogos | python-engineer | T1 | 2 | escrita |
| T6 | Saídas e Markdown: tabela de resultado, erro, stream, paleta de sintaxe nova | python-engineer | T1 | 2 | escrita |
| T7 | Ícones da interface trocados por desenhos Tabler com ponta/junção retas | python-engineer | T1 | 2 | escrita |
| T8 | Logo (BrandMark) e favicons claro/escuro no conceito escolhido | python-engineer | T1, D1 | 3 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2 → T3 → T4 → T5 → T6 → T7
- Wave 3 (serial, escrita): T8 — bloqueada até o operador escolher o logo (D1)

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Logo: **P13.3 N-Block** (`logos/03-n-block.svg` / `-dark.svg`) — trocado pelo operador em 2026-11-10 no teste do commit `0ef4ee7` (antes: P13.1 Spark Spiral) | conceito é escolha de marca do operador | sem evidência — preferência do operador | manter o "N" em grade atual |
| D2 | Fontes via pacotes `@fontsource` (space-grotesk, public-sans, archivo-black) importados em `main.tsx`, como já é feito com a JetBrains Mono | Inter era declarada e não empacotada — o app renderiza na fonte do sistema | `frontend/src/main.tsx:6-8`; inventário (Inter→SF Pro) | Google Fonts via CDN (app é local/offline) |
| D3 | Ícones Tabler copiados como paths SVG nos `icons.tsx`, sem dependência nova | mantém o padrão atual de SVG inline e zero runtime extra | `frontend/src/components/shell/icons.tsx` | pacote `@tabler/icons-react`; Phosphor (pontas arredondadas, incompatível com cantos retos) |
| D4 | Paleta de sintaxe do export HTML: **(b) manter a antiga** — decidido pelo operador em 2026-11-10; o export diverge do app de propósito | a paleta é duplicada front/back por decisão anterior; sem (a) o export diverge do app | memória `export-html-realca-codigo-com-pygments-e-paleta-do-app` | — |
| D5 | Rótulos das células mantêm o texto atual, só em maiúsculas via CSS | só visual; o "PYSPARK" do mockup não é adotado | `frontend/src/components/notebook/CellHeader.tsx` | renomear para PYSPARK |
| D6 | Botão único: o `.btn` global passa a ter o estilo novo e o escopo `.neo` deixa de carregar regras próprias | hoje convivem dois estilos (azul antigo em painéis/Home) | inventário seção 6 | manter dois estilos |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Build sem erro | `cd frontend && npm run build` → exit 0 | constraint |
| T1 | Nenhum canto arredondado no CSS | `grep -rnE "border-radius:\s*[^0;]" frontend/src` → sem saída (só `0`) | feature |
| T1 | Tokens claro com os hex do mockup | `grep -niE "#FEFEEE|#FDE68A|#F6F5DF" frontend/src/styles/tokens.css` → presentes | feature |
| T1 | Tokens escuro suaves | `grep -niE "#2B2A31|#35343C|#E8E4DA|#CFC9BC|#1B1A20" frontend/src/styles/tokens.css` → presentes | feature |
| T1 | Fontes empacotadas | `grep -nE "@fontsource/(space-grotesk|public-sans|archivo-black)" frontend/src/main.tsx frontend/package.json` → presentes | feature |
| T1 | Sem sombras com blur nem tokens creme antigos | `grep -rniE "#d8d2c4|#a8a091|#3a3936|--shadow-(sm|md|lg)" frontend/src` → sem saída | refactor |
| T1 | Primário não é mais azul | `grep -n "btn-primary" -A6 frontend/src/styles/global.css` → sem `--color-accent` no background | feature |
| T2 | Rail e cabeçalho de painel usam o fundo do app | `grep -nE "\.rail|\.panelHeader|\.panel" -A8 frontend/src/components/shell/AppShell.module.css` → `background` = token de fundo do app | feature |
| T2 | Medidor RAM/CPU/Disk sem tracejado | `grep -rn "dashed" frontend/src/components/shell/AppShell.module.css` → nenhuma ocorrência nas regras do medidor | feature |
| T2 | Aba ativa usa a superfície | regra da aba ativa em `AppShell.module.css` → `background: var(--color-surface)` (ou token equivalente de superfície) | feature |
| T3 | Faixa por tipo de célula | `grep -nE "data-cell-type|cellType" frontend/src/components/notebook/CellHeader.tsx frontend/src/components/notebook/Notebook.module.css` → atributo no header e 4 regras de cor | feature |
| T7 | Ícones com cantos retos | `grep -nE "stroke-linecap|strokeLinecap|stroke-linejoin|strokeLinejoin" frontend/src/components/*/icons.tsx` → `square`/`miter`, sem `round` | feature |
| T8 | Logo e favicons novos | `frontend/public/favicon-light.svg` e `favicon-dark.svg` sem `rx=`; `BrandMark` em `shell/icons.tsx` sem `rx` | feature |
| T6 | Paleta de sintaxe nova no app | `grep -niE "#7C3AED|#15803D|#C9BEF5|#A3DDB3" frontend/src/components/notebook/Notebook.module.css frontend/src/styles/tokens.css` → presentes | feature |
| T1 | Nada fora do visual mudou | `git diff --stat <baseline> -- frontend/src/api frontend/src/state frontend/src/ws backend` → vazio (exceto `backend/src/notisbook/export/html_report.py` se D4=a) | constraint |
| T3 | Typecheck limpo | `cd frontend && npm run typecheck` → exit 0 | constraint |
| T2 | (review r1) Filhos com cor própria herdam `--on-fill` em item de menu/seletor em destaque | `grep -nE "color: inherit|--on-fill" frontend/src/components/shell/Menu.module.css frontend/src/components/kernel/Kernel.module.css` → regra para `.check` em item hover/foco e para `.selectorKernel`/`.selectorCaret` em destaque | fix |
| T4 | (review r1) Glifo de variável legível no foco da linha | regra `.row:focus-visible` em `VariablesPanel.module.css` não deixa `.glyph` com `--on-fill` sobre `--color-surface` | fix |
| T3 | (review r2) Gatilho "⋮" do cabeçalho de célula legível sobre a faixa pastel | regra em `Notebook.module.css` dá `--on-fill`/`inherit` ao gatilho de menu dentro de `.cellHeader` | fix |
| T6 | (review r2) Código inline legível em blockquote/th do Markdown | `grep -n "\.markdown code" -A4 frontend/src/components/outputs/Markdown.module.css` → define `color` | fix |
| T6 | (review r2) Sem mapeamento de sintaxe duplicado nem token sem uso | `grep -c "var(--sx-kw)" frontend/src/components/notebook/Notebook.module.css` → 1; `grep -rn "\-\-sx-const\|\-\-aqua" frontend/src` → sem saída ou com uso | fix |
| T1 | (review r3) Sem aliases de token sem uso | `for t in cell-border dialog-shadow btn-shadow canvas-dot; do grep -rn "var(--$t)" frontend/src; grep -n "\-\-$t:" frontend/src/styles/tokens.css; done` → sem saída | fix |
| T6 | (review r1) Paleta de sintaxe em um lugar só | `grep -nE "var\(--sx-" frontend/src/components/notebook/Notebook.module.css` → presentes; `grep -cE "#7c3aed|#c9bef5" frontend/src/components/notebook/Notebook.module.css` → 0 | fix |

## Arquivos previstos
- `frontend/src/styles/tokens.css` — T1
- `frontend/src/styles/global.css` — T1
- `frontend/src/styles/dialog.module.css` — T1
- `frontend/src/main.tsx` — T1
- `frontend/package.json` — T1
- `frontend/package-lock.json` — T1
- `frontend/src/components/shell/AppShell.module.css` — T2
- `frontend/src/components/shell/Banner.module.css` — T2
- `frontend/src/components/shell/Menu.module.css` — T2
- `frontend/src/components/shell/StatusScreen.module.css` — T2
- `frontend/src/components/notebook/Notebook.module.css` — T3, T6
- `frontend/src/components/notebook/CellHeader.tsx` — T3
- `frontend/src/components/kernel/Kernel.module.css` — T3
- `frontend/src/components/data/DataPanel.module.css` — T4
- `frontend/src/components/files/FileBrowser.module.css` — T4
- `frontend/src/components/files/Breadcrumb.module.css` — T4
- `frontend/src/components/variables/VariablesPanel.module.css` — T4
- `frontend/src/components/settings/SettingsPage.module.css` — T5
- `frontend/src/components/spark/Spark.module.css` — T5
- `frontend/src/components/outputs/Outputs.module.css` — T6
- `frontend/src/components/outputs/Markdown.module.css` — T6
- `backend/src/notisbook/export/html_report.py` — T6 (só se D4 = a)
- `frontend/src/components/shell/icons.tsx` — T7, T8
- `frontend/src/components/notebook/icons.tsx` — T7
- `frontend/src/components/kernel/icons.tsx` — T7
- `frontend/public/favicon-light.svg` — T8
- `frontend/public/favicon-dark.svg` — T8

## Fora de escopo
- Elementos que o mockup inventou e não existem hoje: botões de Variables/Settings no rail, texto "Run all · Restart kernel · Interrupt" na barra, pílula "Interrupted", segunda aba de exemplo — exigiriam comportamento novo.
- Mudanças de backend além da paleta de exportação (D4) — o operador tratará backend em outra rodada.
- Tabela de resultado do DataFrame (CSS embutido em `frontend/src/components/outputs/HtmlOutput.tsx`) — adiada pelo operador para depois.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/api/**`, `frontend/src/state/**`, `frontend/src/ws/**`, `frontend/src/lib/**` e todo `backend/**` (salvo `html_report.py` com D4 = a).
- Textos e rótulos da interface, atalhos de teclado, formato do `.ipynb`, ordem/estrutura do DOM além de classes/atributos de estilo.
- Fonte do código (JetBrains Mono).

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6  - [x] T7  - [x] T8

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer (T1) | OK | 164783 | 79827 |
| 2 | python-engineer (T2-T4) | OK | 196318 | 109068 |
| 2 | python-engineer (T5-T7) | OK | 147304 | 85062 |
<!-- effort-ledger:end -->
