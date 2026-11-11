# Pendências cosméticas — menu de contexto e pasta dos notebooks

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

## Objetivo

Nits do code review do plano `menu-contexto-raiz-notebooks`, fora do gatilho do loop.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `backend/src/notisbook/notebooks/store.py:228` — delete de não-.ipynb responde "Only .ipynb files can be written"; usar "…can be deleted" | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/notebooks/store.py:231` — `PartialDelete` também em falha de `unlink` e ecoa caminho absoluto; "Partially deleted" só no `rmtree`, senão "Could not delete" com `strerror` | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/config.py:58` — `root_source: str`; tipar `Literal["cli","saved","default"]` | python-engineer | — | 1 | escrita |
| T5 | `backend/src/notisbook/kernels/service.py:625` — `has_session_under` compara caminhos resolvidos, mas APFS é case-insensitive: `A.ipynb` × `a.ipynb` escapa; comparar identidade com `os.path.samestat` | python-engineer | — | 1 | escrita |
| T6 | `frontend/src/App.tsx:41` — falha em `GET /api/notebooks-root` derruba o boot inteiro; capturar e seguir com `root = null` | python-engineer | — | 1 | escrita |
| T7 | `frontend/src/components/files/FileBrowser.tsx:110-117` — Esc que limpa a seleção é global (`window`); prender ao painel (`onKeyDown` no `div.browser` ou checar `contains(document.activeElement)`) | python-engineer | — | 1 | escrita |
| T8 | `frontend/src/components/files/FileBrowser.tsx:184-190` — após Rename o item perde a seleção; reselecionar o novo caminho depois do `await load()` | python-engineer | — | 1 | escrita |
| T4 | `frontend/src/state/workspace.ts:146` — `loadRoot` homônimo de `useFiles.loadRoot`; renomear para `loadNotebooksRoot`/`applyNotebooksRoot` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Mensagem de delete correta | `grep -n "can be deleted" backend/src/notisbook/notebooks/store.py` → presente | bugfix |
| T2 | "Partially deleted" só no ramo recursivo | leitura de `NotebookStore.delete` | bugfix |
| T3 | `root_source` tipado | `grep -n 'Literal\["cli", "saved", "default"\]' backend/src/notisbook/config.py` → presente | refactor |
| T5 | Alias por caixa bloqueia | servidor de teste: sessão em `a.ipynb` → `DELETE A.ipynb` → 409 | bugfix |
| T6 | Boot sobrevive a falha da raiz | leitura de `App.tsx`: erro de `loadRoot` não leva à tela de erro | bugfix |
| T7 | Esc só limpa seleção com foco no painel | leitura de `FileBrowser.tsx` | bugfix |
| T8 | Item renomeado continua selecionado | leitura de `handleRename` | feature |
| T4 | Sem homônimo | `git grep -n "loadNotebooksRoot" -- frontend/src` → presente | refactor |

## Arquivos previstos
- `backend/src/notisbook/notebooks/store.py` — T1, T2
- `backend/src/notisbook/config.py` — T3
- `frontend/src/state/workspace.ts` — T4
- `backend/src/notisbook/kernels/service.py` — T5
- `frontend/src/App.tsx` — T6
- `frontend/src/components/files/FileBrowser.tsx` — T7, T8

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Contratos HTTP do delete e da raiz.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6  - [ ] T7  - [ ] T8

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T2 resolvido (unlink falho → 409 sem caminho)
- T5 resolvido (caixa no APFS)
- T7 resolvido (= arvore #1)
- T8 já estava resolvido
