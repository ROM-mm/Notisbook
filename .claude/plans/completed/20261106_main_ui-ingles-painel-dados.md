# Painel Dados compacto, fix do Unauthorized e UI em inglês

Branch: main   Fluxo: MIXED   Peso: completo

Criação:     2026-11-06 18:15:15 -0300
Modificação: 2026-11-06 21:57:37 -0300
Finalização: 2026-11-06 21:57:37 -0300

## Objetivo

(1) Compactar o painel Dados: refresh do CATALOG na linha do título; no FILES, refresh + `+` lado a lado no título, sem o botão "Alterar diretório" (o `+` abre a escolha de pasta). (2) Corrigir o "Unauthorized" do FILES: hoje o store pede `/api/fs/list` do root salvo (localStorage) antes do `bootstrapAuth()` e nunca re-tenta (`state/files.ts:94-95`, `App.tsx:33-36`, `security.py:41`; hipótese forte, não observada em runtime). (3) Traduzir para inglês todo texto pt-BR visível na interface (frontend ~35 arquivos + 3 do backend), por troca direta — sem camada i18n.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Layout do painel Dados: ações no cabeçalho de CATALOG e FILES; `+` (PlusIcon) substitui o botão "Alterar diretório" chamando o mesmo `choose()` | python-engineer | — | 1 | escrita |
| T2 | Root salvo do FILES é (re)carregado só depois da autenticação concluída | python-engineer | — | 2 | escrita |
| T3 | Frontend: todo texto pt-BR visível em inglês (JSX, aria-label/title/placeholder, alert/confirm, mensagens de estado/erro, nomes padrão, `lang` e locale de data) | python-engineer | T1,T2 | 3 | escrita |
| T4 | Backend: textos pt-BR que chegam à tela em inglês (`native_picker.py`, `sql_cell.py`, `static.py`) | python-engineer | — | 4 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3
- Wave 4 (serial, escrita): T4

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Nomes padrão viram "Untitled" / "New folder" | coerência com UI em inglês; arquivos existentes não mudam | `state/workspace.ts:137`, `files/FileBrowser.tsx:180,185`, `lib/paths.ts:40` | manter pt-BR — descartado (UI mista); recomendação do tech-lead, operador pode reverter antes da wave 3 |
| D2 | `lang="en"` e formatação de data/hora em `en-US` | sem isso "há 5 minutos"/datas seguem em pt-BR | `index.html:2`, `static.py:22`, `files/format.ts:3-4`, `spark/InstallPanel.tsx:14`, `files/FileBrowser.tsx:30` | locale do navegador (`undefined`) — descartado por previsibilidade; recomendação do tech-lead |
| D3 | Troca direta dos literais, sem lib i18n | pedido é "tudo em inglês", não multilíngue; i18n seria arquitetura nova | inventário: nenhum mecanismo i18n no repo | react-i18next/catálogo — descartado (fora do pedido) |
| D4 | Frontend React implementado pelo `python-engineer` | harness sem especialista de frontend; precedente nos planos anteriores deste repo | `completed/20261106_main_erros-e-avisos-spark-concisos.md` T2 | — |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Refresh do Catalog dentro do header da seção, sem linha `.sectionActions` própria | `CatalogSection.tsx`: botão `RefreshIcon` é descendente do mesmo container do `<h3>`; `grep -n "sectionActions" frontend/src/components/data/CatalogSection.tsx` não mostra linha separada abaixo do header | feature |
| T1 | Header do Files com refresh e `+` lado a lado; botão "Alterar diretório"/"Selecionar diretório" removido | `grep -n "PlusIcon" frontend/src/components/data/FilesSection.tsx` ≥1; `grep -rn "Alterar diretório\|Selecionar diretório" frontend/src` vazio | feature |
| T1 | `+` dispara a mesma escolha de pasta (`chooseDirectory` / `POST /api/fs/choose-dir`) | `FilesSection.tsx`: onClick do botão `+` chama `choose` | constraint |
| T2 | Listagem do root salvo só é disparada após `bootstrapAuth()` resolver (ou re-disparada após ela) | `state/files.ts`/`App.tsx`: `load(root)` inicial acoplado à conclusão do auth; `grep -n "queueMicrotask" frontend/src/state/files.ts` não agenda load na criação do store | bugfix |
| T2 | Após restart do servidor com root salvo, FILES lista o diretório sem "Unauthorized" | teste manual: reiniciar backend, abrir app, painel FILES mostra o conteúdo do último diretório | bugfix |
| T3 | Nenhum texto visível pt-BR restante no frontend | `grep -rnP "[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]" frontend/src --include=*.tsx --include=*.ts` só retorna comentários | feature |
| T3 | `lang` e locales em inglês | `grep -rn "pt-BR" frontend/index.html frontend/src` só em comentários | feature |
| T3 | Build do frontend verde | `cd frontend && npm run build` exit 0 | constraint |
| T4 | Textos de tela do backend em inglês | `grep -nP "[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]" backend/src/notisbook/files/native_picker.py backend/src/notisbook/kernels/sql_cell.py backend/src/notisbook/static.py` só em comentários/docstrings | feature |
| T4 | Backend importa sem erro | `cd backend && python -c "import notisbook.files.native_picker, notisbook.kernels.sql_cell, notisbook.static"` exit 0 | constraint |
| T3 | Badge do Catalog sem "desatualizado" (review r1) | `grep -n "desatualizado" frontend/src/components/data/CatalogSection.tsx` vazio | bugfix |
| T3 | Placeholder do DirectoryPicker em inglês (review r1) | `grep -n "caminho/absoluto" frontend/src/components/data/DirectoryPicker.tsx` vazio | bugfix |

## Arquivos previstos
- `frontend/src/components/data/CatalogSection.tsx` — T1, T3
- `frontend/src/components/data/FilesSection.tsx` — T1, T3
- `frontend/src/components/data/DataPanel.module.css` — T1
- `frontend/src/state/files.ts` — T2
- `frontend/src/App.tsx` — T2, T3
- `frontend/index.html` — T3
- `frontend/src/**/*.tsx`, `frontend/src/**/*.ts` com texto pt-BR do inventário (components/{shell,notebook,files,spark,kernel,outputs,settings,data}, state/{kernel,workspace,notebook,catalog}.ts, lib/paths.ts, ws/jobs.ts, components/files/format.ts) — T3
- `backend/src/notisbook/files/native_picker.py` — T4
- `backend/src/notisbook/kernels/sql_cell.py` — T4
- `backend/src/notisbook/static.py` — T4

## Fora de escopo
- Saídas já gravadas em `.ipynb` (rodapés "N linhas", erros antigos) — são dados, não UI.
- Comentários, docstrings e identificadores em pt-BR — não aparecem na tela.
- Camada i18n / suporte multilíngue — D3.
- Testes automatizados — repo não tem suíte; nenhum teste será criado.
- **Documentação de produto** — README/docs que descrevam a UI em pt-BR ("Alterar diretório", "Dados") ficam desatualizados; reportado ao operador no fim, não corrigido aqui.

## Não mexer
- Códigos de máquina em inglês: `"busy"` (`state/catalog.ts:71`, `api/catalog.py:56`), prefixo `failed:` (`spark/JobProgress.tsx:39`), código `(-128)` (`native_picker.py:15,88`).
- Matching de erro Spark em `components/outputs/sparkError.ts` e filtros log4j em `spark/bundles.py`.
- Mecanismo de autenticação do backend (`security.py`, `config.py`).
- Persistência do root em localStorage (`notisbook.files.root`).
- Atributos `data-testid`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 54271 | 45409 |
| 0 | knowledge-engineer | OK | 199802 | 86773 |
| 1-2 | python-engineer | OK | 51862 | 43788 |
| 3 | python-engineer | OK | 164086 | 90736 |
| 4 | python-engineer | OK | 25171 | 32068 |
| review-r1 | code-review | ajustes necessários | 105256 | 99229 |
| fix-r1 | python-engineer | OK | 15326 | 25419 |
| review-r2 | code-review | aprovar | 71920 | 80919 |
| audit | plan-auditor | OK | 51896 | 30102 |
| close | memory-manager | OK | 24959 | 50338 |
<!-- effort-ledger:end -->
