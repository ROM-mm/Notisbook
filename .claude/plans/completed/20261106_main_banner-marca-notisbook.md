# Banner da marca notisbook, ícone Grid-N (H) e favicon por tema

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-06 22:39:29 -0300
Modificação: 2026-11-06 22:52:39 -0300
Finalização: 2026-11-06 22:52:39 -0300

## Objetivo

Dar identidade visual ao app: faixa de 56px no topo (acima das abas, largura total) com o ícone Grid-N variação H (monograma 4×4 de blocos colados: colunas na cor de frente, diagonal na cor de destaque), wordmark "notisbook" (minúsculo só no banner), separador, a frase "Explore. Code. Transform." e uma decoração sutil de fluxo com nós à direita. Tudo segue o tema (claro/escuro/sistema) via variáveis CSS. O mesmo ícone substitui o `LogoMark` da barra lateral e vira favicon claro/escuro, trocado por JS conforme o tema efetivo do app (SVG favicon sozinho só segue o tema do SO). Referência visual aprovada: rascunho v3, variação H (fora do repo).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Componente do ícone H (SVG inline) com cores por tokens de tema; substitui `LogoMark` na `StatusScreen` (ampliação pedida pelo operador); a barra lateral deixa de ter logo (deduplicação pedida pelo operador) | python-engineer | — | 1 | escrita |
| T2 | Banner no topo do `AppShell`, antes do `TabBar`: ícone + wordmark + separador + frase + decoração, temável | python-engineer | T1 | 2 | escrita |
| T3 | Favicon H claro e escuro em `frontend/public/`, `<link rel="icon">` no `index.html` e troca do href pelo tema efetivo em `state/theme.ts` | python-engineer | T1 | 3 | escrita |
| T4 | Deduplicar a marca: remover o logo do topo da barra lateral e o título "Notisbook" de fallback da Topbar (o banner já mostra a marca) | python-engineer | T1,T2 | 4 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3
- Wave 4 (serial, escrita): T4

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Ícone Grid-N variação H | escolha do operador após 3 rodadas de rascunho; foge do visual Databricks (camadas/laranja) | sem evidência — preferência do operador | "N_", n de pipeline, medalhão, run-disk, flow-blocks, cell-rows, Grid-N A–G |
| D2 | Cores por tokens CSS novos (fundo do ícone, frente, destaque) em `tokens.css` nas 4 variantes de tema; escuro: fundo escuro, colunas brancas, destaque verde-limão `#C4F542`; claro: fundo claro, colunas escuras, destaque verde fechado `#7FB800` | tema já é 100% CSS vars (light default, OS-dark, forced dark/light) | `styles/tokens.css:11,95-96,131,165`; `state/theme.ts:21-25` | cores fixas — descartado (não acompanha tema) |
| D3 | Banner como 1ª linha do shell, largura total, `flex:none`, 56px | pedido "acima das abas"; shell é flex column TabBar→Topbar→body | `components/shell/AppShell.tsx:25-43`, `AppShell.module.css:3-17,140-150` | só sobre a coluna de conteúdo — exigiria reestruturar o shell |
| D4 | Favicon: dois SVG estáticos (claro/escuro) e troca do `href` em JS pelo `effectiveTheme` | favicon SVG com media query só segue o SO, não o tema forçado no app | `state/theme.ts:27-32,60`; CSP `img-src 'self'` em `backend/src/notisbook/static.py:12-16` | um SVG com `prefers-color-scheme` — descartado (ignora tema forçado) |
| D5 | Wordmark "notisbook" minúsculo só no banner; "Notisbook" segue no resto | escolha do operador | sem evidência — preferência do operador | renomear em todo o app |
| D6 | Implementação pelo `python-engineer` | decisão registrada do operador para back+front deste repo | memória `python-engineer-implementa-back-e-front` | — |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Componente do ícone H exportado e usado no banner e na StatusScreen | `grep -rn "BrandMark" frontend/src` mostra definição + usos em Banner.tsx e StatusScreen.tsx | feature |
| T1 | `StatusScreen` usa o ícone H e `LogoMark` deixa de existir (ampliação) | `grep -rn "LogoMark" frontend/src` vazio; `grep -n "BrandMark" frontend/src/components/shell/StatusScreen.tsx` ≥1 | feature |
| T1 | Cores do ícone vêm de tokens nas variantes de tema | `grep -n "brand" frontend/src/styles/tokens.css` mostra os tokens em `:root`, bloco `prefers-color-scheme: dark`, `[data-theme="dark"]` e `[data-theme="light"]` | feature |
| T2 | Banner renderizado antes do `TabBar` no `AppShell`, 56px, `flex:none` | `AppShell.tsx`: elemento do banner precede `<TabBar` ; CSS do banner com `height: 56px` | feature |
| T2 | Banner contém wordmark e frase exatos | `grep -rn "notisbook\|Explore. Code. Transform." frontend/src/components/shell` | feature |
| T2 | Banner e decoração usam só variáveis de tema (sem hex fixo no CSS/SVG do banner) | `grep -nE "#[0-9a-fA-F]{3,6}" <arquivos do banner>` vazio | constraint |
| T2 | Visual acompanha troca de tema | teste manual: View → tema claro/escuro/sistema; banner e ícone trocam de cores sem recarregar | feature |
| T4 | Barra lateral sem logo no topo (ampliação) | `grep -n "BrandMark\|styles.logo" frontend/src/components/shell/Sidebar.tsx` vazio | feature |
| T4 | Topbar não mostra "Notisbook" quando nenhum notebook está aberto (ampliação) | `grep -n '"Notisbook"' frontend/src/App.tsx frontend/src/components/shell/Topbar.tsx` sem uso como título da topbar; títulos de notebook/Settings seguem | feature |
| T3 | Dois favicons e link declarado | `ls frontend/public/favicon-light.svg frontend/public/favicon-dark.svg` exit 0; `grep -n 'rel="icon"' frontend/index.html` ≥1 | feature |
| T3 | Favicon troca com o tema efetivo do app (inclusive forçado e mudança do SO) | `grep -n "favicon" frontend/src/state/theme.ts` mostra a troca no aplicar do tema e no listener do SO; teste manual: forçar tema e ver a aba do navegador | feature |
| T3 | Build verde | `cd frontend && npm run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/src/components/shell/icons.tsx` — T1
- `frontend/src/components/shell/Sidebar.tsx` — T1
- `frontend/src/components/shell/StatusScreen.tsx` — T1
- `frontend/src/components/shell/AppShell.module.css` — T1, T2
- `frontend/src/styles/tokens.css` — T1
- `frontend/src/components/shell/Banner.tsx` — T2
- `frontend/src/components/shell/Banner.module.css` — T2
- `frontend/src/components/shell/AppShell.tsx` — T2
- `frontend/public/favicon-light.svg` — T3
- `frontend/public/favicon-dark.svg` — T3
- `frontend/index.html` — T3
- `frontend/src/state/theme.ts` — T3
- `frontend/src/components/shell/Sidebar.tsx` — T4
- `frontend/src/components/shell/AppShell.module.css` — T4
- `frontend/src/App.tsx` — T4
- `frontend/src/components/shell/Topbar.tsx` — T4

## Fora de escopo
- Banner recolhível/fechável — não pedido.
- Renomear "Notisbook" para minúsculo fora do banner (D5).
- Ícones de app nativo (PNG/ICNS, apple-touch-icon) — só favicon SVG.
- **Documentação de produto** — README/docs não mostram o banner nem o novo logo; reportado ao operador no fim, não corrigido aqui.

## Não mexer
- Mecanismo de tema (`data-theme`, chave `notisbook.theme`, `initTheme`/`applyPref` além do acréscimo do favicon).
- CSP do backend (`backend/src/notisbook/static.py`).
- Ordem `TabBar` → `Topbar` → body; só se acrescenta o banner antes.
- Textos de UI existentes (seguem em inglês).

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 52443 | 40469 |
| 1-3 | python-engineer | FAILED (sem commit; código pronto) | 64612 | 46384 |
| review-r1 | code-review | aprovar (4 nits) | 55905 | 64317 |
| 1 (ampliação) | python-engineer | OK | 20198 | 28443 |
| 4 | python-engineer | OK | 32960 | 32956 |
| review-r2 | code-review | aprovar (nits) | 39904 | 61878 |
| audit | plan-auditor | OK | 30721 | 30663 |
| close | memory-manager | OK | 18395 | 47031 |
<!-- effort-ledger:end -->
