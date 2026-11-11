# Pendências cosméticas — banner da marca

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 22:44:12 -0300
Modificação: 2026-11-06 22:47:06 -0300
Finalização: —

## Objetivo

Nits do code review do plano banner-marca-notisbook: acessibilidade do landmark, tokens redundantes e CSS/comentário sem efeito.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/components/shell/Banner.tsx:7` — `<header>` duplica landmark banner com Topbar e `aria-label` repete o wordmark; usar `<div>` ou remover `aria-label` | python-engineer | — | 1 | escrita |
| T2 | `frontend/src/styles/tokens.css:181-184` — `--brand-mark-*` repetidos em `[data-theme="light"]`; remover | python-engineer | — | 1 | escrita |
| T3 | `frontend/src/components/shell/Banner.module.css:1` — comentário "Só variáveis de tema" impreciso; ajustar para "cores só via variáveis" | python-engineer | — | 1 | escrita |
| T4 | (resolvido no T4 do plano principal — `.logo` removido) `frontend/src/components/shell/AppShell.module.css:37` | python-engineer | — | 1 | escrita |
| T5 | `frontend/src/components/shell/Topbar.tsx:181` — `title: ReactNode \| null` redundante; voltar a `ReactNode` | python-engineer | — | 1 | escrita |
| T6 | `frontend/src/components/shell/Topbar.tsx:190-199` — home sem `<h1>` (começa em `<h2>` da Home:68); promover a h1 ou h1 sr-only | python-engineer | — | 1 | escrita |
| T7 | `frontend/src/components/shell/Topbar.tsx:195-197` — "Run all" desabilitado aparece só em Settings; manter só no NotebookHeading | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T5, T6, T7

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Sem landmark banner duplicado | `grep -n "<header\|aria-label" frontend/src/components/shell/Banner.tsx` sem `<header` com `aria-label` | refactor |
| T2 | Sem tokens repetidos no claro forçado | `sed -n '175,190p' frontend/src/styles/tokens.css` sem `--brand-mark` | refactor |
| T3 | Comentário preciso | `grep -n "Só variáveis de tema" frontend/src/components/shell/Banner.module.css` vazio | refactor |
| T4 | `.logo` sem color morto | `grep -n -A6 "^\.logo" frontend/src/components/shell/AppShell.module.css` sem `color:` | refactor |
| T5 | Tipo sem null redundante | `grep -n "ReactNode | null" frontend/src/components/shell/Topbar.tsx` vazio | refactor |
| T6 | Home tem h1 | `grep -rn "<h1" frontend/src/App.tsx frontend/src/components` mostra h1 renderizado na home | refactor |
| T7 | Run all só com notebook | `grep -n "run-all" frontend/src/components/shell/Topbar.tsx` só dentro do ramo de notebook | refactor |

## Arquivos previstos
- `frontend/src/components/shell/Banner.tsx` — T1
- `frontend/src/styles/tokens.css` — T2
- `frontend/src/components/shell/Banner.module.css` — T3
- `frontend/src/components/shell/Topbar.tsx` — T5, T6, T7

## Fora de escopo
- Mudança visual do banner.
- **Documentação de produto** — nenhuma.

## Não mexer
- Cores e geometria do ícone; favicons.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [x] T4  - [ ] T5  - [ ] T6  - [ ] T7

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T4 já resolvido; T7 obsoleto (Run all virou item do menu)
