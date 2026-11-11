# Visual em cartão — Environments, Config e diálogos

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 11:09:09 -0300
Modificação: 2026-11-10 11:21:04 -0300
Finalização: 2026-11-10 11:21:04 -0300

## Objetivo

Levar o padrão visual das células (memória: células em cartão neo-brutalista suave) para a página Spark environments (Settings) e os 4 diálogos, conforme mockups aprovados (environments-v1, config-modal-v1): cartões com borda 2px suavizada, raio 16px, sombra creme e cabeçalho com linha inferior; fundo pontilhado; job ativo com sombra escura; pílulas contornadas; barra de progresso contornada com preenchimento preto; botões e campos com borda 1.5px e mini-sombra creme, primário preto; diálogos numa folha única com sombra sólida grafite. Só visual — textos, comportamento e regras de habilitação intactos. O botão novo vale só nessas telas/diálogos; a `.btn` global não muda nesta rodada (14 arquivos a usam e o resto da aplicação ainda não foi desenhado).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Tokens `--dialog-shadow` e `--btn-shadow` no tema claro e nos dois escuros | python-engineer | — | 1 | escrita |
| T2 | Folha de diálogo compartilhada; os 4 diálogos migram para ela; `.dialog` duplicado sai de Spark.module.css e AppShell.module.css | python-engineer | T1 | 1 | escrita |
| T3 | Página Settings/Spark: fundo pontilhado, cartões com cabeçalho, job ativo com sombra escura, pílulas contornadas, progresso contornado | python-engineer | T1 | 1 | escrita |
| T4 | Botões e campos no estilo novo, escopados à página Settings e aos 4 diálogos; primário preto | python-engineer | T1 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3 → T4

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Estilo novo de botão escopado às telas desta rodada | `.btn` global é usada em 14 arquivos; mudá-la restilizaria telas ainda não desenhadas | `grep -rl '"btn' frontend/src` = 14 arquivos | mudar a `.btn` global já |
| D2 | Uma folha única de diálogo para os 4 diálogos | `.dialog` duplicado | `Spark.module.css:378-395`, `AppShell.module.css:359-371` | restilizar as duas cópias |
| D3 | Primário preto (azul só para seleção/"in use"), modal com sombra grafite, progresso preto | mockup aprovado | sem evidência — aprovação do operador nos mockups | primário azul; sombra creme no modal |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Tokens novos nos 3 blocos de tema | `grep -c -- "--dialog-shadow:" frontend/src/styles/tokens.css` ≥ 3; idem `--btn-shadow:` | feature |
| T2 | Os 4 diálogos importam a folha compartilhada | `grep -l "dialog.module.css" frontend/src/components/spark/PackagesDialog.tsx frontend/src/components/spark/AddLibraryDialog.tsx frontend/src/components/shell/AboutDialog.tsx frontend/src/components/shell/ShortcutsDialog.tsx` lista os 4 | refactor |
| T2 | Sem `.dialog {` duplicado | `grep -n "^\.dialog {" frontend/src/components/spark/Spark.module.css frontend/src/components/shell/AppShell.module.css` sem saída | refactor |
| T2 | Diálogo com borda 2px, raio 16px e sombra grafite | `grep -A14 "^\.dialog {" frontend/src/styles/dialog.module.css` (janela ampliada de 8→14 na rodada 1 da auditoria: o `composes: neo` empurrou a sombra para a linha 9) mostra `2px solid var(--cell-border)`, `16px` e `var(--dialog-shadow)` | feature |
| T3 | Cartão `.block` no padrão das células | `grep -A8 "^\.block {" frontend/src/components/spark/Spark.module.css` mostra `2px solid var(--cell-border)`, `16px` e `6px 6px 0 var(--cell-shadow)` | feature |
| T3 | Página com fundo pontilhado | `grep "radial-gradient" frontend/src/components/settings/SettingsPage.module.css` encontra `var(--canvas-dot)` | feature |
| T4 | Botões das telas desta rodada usam a mini-sombra | `grep -c "var(--btn-shadow)" frontend/src/components/spark/Spark.module.css frontend/src/styles/dialog.module.css` ≥ 1 no total | feature |
| T4 | Hover do botão destrutivo mantém o fundo de perigo dentro do escopo `.neo` | `grep -n "dangerBtn" frontend/src/components/spark/Spark.module.css` mostra a regra de hover com especificidade ≥ `.neo :global(.btn):hover:not(:disabled)` (ex.: `.dangerBtn:global(.btn):hover:not(:disabled)`) contendo `--color-danger-subtle` | bugfix |
| T4 | `.btn` global intocada | `git diff <baseline> -- frontend/src/styles/global.css` vazio | constraint |
| T1 | Build do frontend passa | `npm --prefix frontend run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/src/styles/tokens.css` — T1
- `frontend/src/styles/dialog.module.css` — T2
- `frontend/src/components/spark/PackagesDialog.tsx` — T2
- `frontend/src/components/spark/AddLibraryDialog.tsx` — T2
- `frontend/src/components/shell/AboutDialog.tsx` — T2
- `frontend/src/components/shell/ShortcutsDialog.tsx` — T2
- `frontend/src/components/shell/AppShell.module.css` — T2
- `frontend/src/components/spark/Spark.module.css` — T2, T3, T4
- `frontend/src/components/settings/SettingsPage.module.css` — T3
- `frontend/src/components/spark/PrereqsPanel.tsx` — T3, T4
- `frontend/src/components/spark/InstallPanel.tsx` — T3, T4
- `frontend/src/components/spark/InstalledList.tsx` — T3, T4
- `frontend/src/components/spark/JobProgress.tsx` — T3, T4

## Fora de escopo
- Resto da aplicação (topbar, abas, painel lateral, painéis de dados, navegador de arquivos) e a `.btn` global — próximas rodadas da padronização.
- String "encontrado" em português em `PrereqsPanel.tsx:31` e indentação quebrada em `InstalledList.tsx:95-106` — reportadas, não corrigidas.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/styles/global.css`.
- `frontend/src/components/spark/usePackages.ts`, `frontend/src/components/spark/useSparkData.ts`, `backend/**`; textos e lógica de habilitação nos `.tsx` (só `className`/import de estilo podem mudar).
- `frontend/src/components/notebook/**`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 112076 | 66482 |
| 1 | python-engineer | OK | 18302 | 26934 |
<!-- effort-ledger:end -->
