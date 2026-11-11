# Painel Dados abaixo do menu (layout Databricks)

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-05 13:22:37 -0300
Modificação: 2026-11-05 13:44:12 -0300
Finalização: 2026-11-05 13:44:12 -0300

## Objetivo

Hoje o rail de ícones e o painel lateral ocupam a altura toda da janela. Isso acontece porque `.shell` é uma linha flex e tanto o rail quanto o painel são irmãos da coluna `.main`, que contém abas, cabeçalho e células (diagnóstico do knowledge-engineer em `AppShell.tsx:21-44` e `AppShell.module.css`). O objetivo é reorganizar o layout no padrão Databricks:

- linha 1: abas, na largura toda;
- linha 2: cabeçalho do notebook (título e seletor de kernel) mais o menu, na largura toda;
- abaixo dessas duas linhas: rail de ícones, painel lateral e células, lado a lado.

O logo continua no topo do rail, conforme aceito pelo operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|---|---|---|---|---|---|
| T1 | Reestruturar `AppShell`: `.shell` passa a ser coluna (TabBar, depois topbar, depois uma linha flex nova com rail, painéis e `main.content`), preservando a cadeia `flex: 1` / `min-height: 0` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Decisões
| id | decisão | motivo | evidência | sucede |
|---|---|---|---|---|
| D1 | Ordem: abas, depois cabeçalho e menu, depois a linha de baixo | O Topbar mostra a aba ativa (`App.tsx:98`, `Topbar.tsx:186`). Por isso fica abaixo das abas | `sem evidência — aceite do operador` | — |
| D2 | O logo fica no topo do rail | Mantém o plano em 2 arquivos | `sem evidência — aceite do operador` | — |
| D3 | `python-engineer` implementa o React/TS | O harness não tem agente de frontend, igual aos planos anteriores | `sem evidência — aceite do operador` | — |

## Critérios de aceite
| id | critério | verificação | tipo |
|---|---|---|---|
| T1 | Shell em coluna | `grep -nE "flex-direction: *column" frontend/src/components/shell/AppShell.module.css` mostra a regra em `.shell` (leitura do código) | feature |
| T1 | Abas e topbar fora da linha de baixo | `AppShell.tsx`: `TabBar` e o slot `topbar` são filhos diretos do contêiner `.shell`. `Sidebar`, `SidePanel` e `main.content` ficam dentro da nova linha flex (leitura do código) | feature |
| T1 | Cadeia de altura preservada | a nova linha tem `flex: 1` e `min-height: 0`, e `.content` mantém `min-height: 0; overflow: auto` (leitura do `AppShell.module.css`); typecheck e build do frontend com exit 0 | constraint |
| T1 | Rolagem própria de Catalog e Files continua funcionando | no app: com uma pasta grande expandida, só a área de Files rola, o Catalog continua visível e o painel começa abaixo do menu | constraint |
| T1 | Rolagem das células por aba continua funcionando | no app: rolar o notebook A, trocar para a aba B e voltar para A mantém a posição de rolagem de A | constraint |
| T1 | Props do AppShell inalteradas | `git diff -- frontend/src/App.tsx` vazio | constraint |

## Arquivos previstos
- `frontend/src/components/shell/AppShell.tsx` — T1
- `frontend/src/components/shell/AppShell.module.css` — T1

## Fora de escopo
- Mover ou remover o logo (descartado em D2).
- Mudanças visuais em `Topbar.tsx`, `TabBar.tsx`, `SidePanel.tsx` e `DataPanel.*`. Se o recuo da `.topbar` ficar estranho, isso é reportado ao operador e não corrigido aqui.
- Persistir o estado aberto/fechado do painel.
- Testes automatizados: não pedidos.
- **Documentação de produto**: nenhuma. Os comentários de cabeçalho em `AppShell.tsx:1-10` podem ser ajustados, porque estão no próprio arquivo-fonte. O de `App.tsx:2-3`, se ficar desatualizado, é reportado no fim.

## Não mexer
- `frontend/src/App.tsx`, porque a interface `topbar`/`children` do AppShell se mantém.
- `frontend/src/components/data/DataPanel.module.css`, onde está a rolagem própria (R17/R21 do plano anterior).
- `frontend/src/components/notebook/NotebookView.tsx`, onde fica a restauração de `scrollTop`.
- `frontend/src/state/workspace.ts`, que guarda o estado `panel`.

## Status
- [x] T1 — concluído e validado pelo operador (commit 0ae50ce); nit de comentário em .claude/plans/pendencias/TODO-painel-dados-abaixo-do-menu.md

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 76637 | 46740 |
| 1 | python-engineer | OK | 50854 | 33500 |
| review | plan-auditor | OK | 27446 | 23095 |
| review | code-review | OK | 46758 | 61147 |
<!-- effort-ledger:end -->
