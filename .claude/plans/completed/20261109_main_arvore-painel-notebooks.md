# Árvore expansível no painel Notebooks

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-09 11:52:55 -0300
Modificação: 2026-11-09 12:20:23 -0300
Finalização: 2026-11-09 12:20:23 -0300

## Objetivo

O painel Notebooks deixa de navegar para dentro da pasta ao clicar e passa a exibir uma árvore expansível (chevron, filhos indentados), como o painel FILES. Árvore própria sobre `/api/contents` em vez de generalizar o `FileTree` do FILES, que é acoplado a `useFiles`/`FsEntry`/paginação e não tem abrir notebook, rename inline nem criação — generalizá-lo arriscaria regressão no FILES.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Painel Notebooks em árvore expansível (lazy por pasta, filtro pastas+.ipynb, abrir notebook, destaque de aberto/ativo, Rename/Delete em qualquer nível, título fixo com o nome da raiz) | python-engineer | — | 1 | escrita |
| T2 | Alvo de criação de pasta/notebook = pasta selecionada → pasta do notebook selecionado → raiz; recarga só da pasta afetada após criar/renomear/excluir | python-engineer | T1 | 1 | escrita |
| T3 | Troca de raiz pelo + zera a árvore e invalida respostas em voo; rota `/tree/<dir>` expande até `dir` | python-engineer | T1 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Árvore própria `NotebookTree` + store de expandidos/cache por caminho relativo sobre `listDir` | FileTree preso a useFiles/FsEntry/caminho absoluto e paginação; faltam rename, abrir notebook, criação, data-open/active | frontend/src/components/data/FileTree.tsx:146-148; frontend/src/components/files/FileBrowser.tsx:229-233 | generalizar FileTree com props (descartada: risco de regressão no FILES) |
| D2 | Criação na pasta selecionada → pasta do notebook selecionado → raiz | `browseDir` deixa de ser "pasta atual" navegada | sem evidência — decisão do operador | sempre na raiz |
| D3 | Estado de expansão só em memória | mesmo padrão dos tamanhos de painel (reset ao fechar) | sem evidência — decisão do operador | localStorage |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Clique em pasta não navega mais (`setDir` fora do clique da linha) | `grep -n 'setDir(entry.path)' frontend/src/components/files/FileBrowser.tsx` sem resultados | feature |
| T1 | Árvore ARIA com nível por linha e chevron | `grep -rn 'role="tree"\|aria-level' frontend/src/components/files` encontra o componente da árvore | feature |
| T1 | Filhos carregados só ao expandir, via `listDir` | `grep -n 'listDir' frontend/src/state/notebookTree.ts` | feature |
| T1 | Filtro só pastas e `.ipynb` preservado, lista completa mantida para `uniqueName` | `grep -rn "type !== \"file\"" frontend/src/components/files` | constraint |
| T1 | Breadcrumb fora do painel | `grep -n 'Breadcrumb' frontend/src/components/files/FileBrowser.tsx` sem resultados | feature |
| T2 | Criação usa a pasta alvo derivada da seleção, com fallback na raiz | `grep -n 'targetDir' frontend/src/components/files/FileBrowser.tsx` | feature |
| T3 | Troca de raiz zera expandidos/cache e invalida respostas antigas | `grep -n 'generation' frontend/src/state/notebookTree.ts` | feature |
| T3 | Rota `/tree/<dir>` expande até `dir` | `grep -n 'expandTo' frontend/src/App.tsx` | feature |
| T1 | Estado de expansão sem persistência | `grep -n 'persist\|localStorage' frontend/src/state/notebookTree.ts` sem resultados | constraint |
| T1 | `forget(path)` descarta respostas em voo de pastas sob `path` (review rodada 1) | `grep -n 'latest.delete' frontend/src/state/notebookTree.ts` encontra a limpeza dentro de `forget` | bugfix |
| T1 | Pasta já carregada é revalidada ao reexpandir e o Reload não mantém cache velho de pastas recolhidas (review rodada 1) | `frontend/src/state/notebookTree.ts`: `expand` com estado `ready` dispara `reload(dir)`; `reloadAll` apaga de `dirs` as pastas não expandidas | bugfix |
| T2 | `createUntitledNotebook` só recarrega explicitamente a raiz ou pasta em `loading` (sem `listDir` duplicado), com comentário explicando o porquê (review rodada 2) | `grep -n 'status === "loading"' frontend/src/state/workspace.ts` encontra a condição do reload | bugfix |
| T1–T3 | Frontend compila | `cd frontend && npm run typecheck` sai 0 | constraint |

## Arquivos previstos
- `frontend/src/components/files/FileBrowser.tsx` — T1, T2, T3
- `frontend/src/components/files/FileBrowser.module.css` — T1
- `frontend/src/components/files/NotebookTree.tsx` — T1
- `frontend/src/state/notebookTree.ts` — T1, T2, T3
- `frontend/src/state/workspace.ts` — T2, T3
- `frontend/src/App.tsx` — T2, T3
- `frontend/src/components/shell/Topbar.tsx` — T2
- `frontend/src/state/router.ts` — T3

## Fora de escopo
- Arrastar itens entre pastas — não pedido.
- Criação de testes — não pedida.
- **Documentação de produto** — nenhuma. Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- `frontend/src/components/data/FileTree.tsx` e `frontend/src/state/files.ts` — painel FILES intacto.
- `backend/` — nenhuma mudança de API.
- `frontend/src/components/files/Breadcrumb.tsx` — componente permanece (só sai do painel).

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| - | knowledge-engineer | OK | 71652 | 57835 |
| 1 | python-engineer | OK | 154805 | 75372 |
| 1 | plan-auditor | CONFORME | 22819 | 20741 |
| 1 | code-review | ajustes necessários | 128679 | 85393 |
| loop-1 | python-engineer | OK | 18563 | 28575 |
| loop-1 | plan-auditor | CONFORME | 22148 | 21465 |
| loop-1 | code-review | ajustes necessários | 91901 | 78599 |
| loop-2 | python-engineer | OK | 12889 | 25703 |
| loop-2 | plan-auditor | CONFORME | 22822 | 22444 |
| loop-2 | code-review | aprovar | 54026 | 72480 |
| - | memory-manager | OK | 22730 | 48285 |
<!-- effort-ledger:end -->
