# Pendências (nits do code review) — arvore-painel-notebooks

Origem: code review rodada 1, 2026-11-09. Não reimplementados neste plano.

- [ ] `frontend/src/components/files/FileBrowser.tsx:48` — listener global de Esc limpa a seleção da árvore com qualquer Esc da app (ex.: sair do editor de célula); restringir ao foco dentro do painel.
- [ ] `frontend/src/components/files/NotebookTree.tsx:88` — após rename/delete da linha focada o foco vai para o body; focar a linha renomeada ou o vizinho/pai.
- [ ] `frontend/src/components/files/NotebookTree.tsx:54` — rascunho de New folder fica invisível e ativo se um ancestral for recolhido; cancelar o draft no collapse.
- [ ] `frontend/src/components/files/Breadcrumb.tsx` — componente e CSS ficaram sem consumidor (plano manteve por "Não mexer"); decidir remover ou reaproveitar.
- [ ] `frontend/src/components/shell/Topbar.tsx:32` — com notebook ativo, File → New notebook usa a pasta do notebook ativo e ignora a seleção da árvore (comportamento anterior preservado; confirmar se é o desejado).
- [ ] `frontend/src/App.tsx:102` — comentário do efeito da rota descreve o quê, não o porquê (review rodada 2).
- [ ] `frontend/src/state/notebookTree.ts:104` — `expandTo` refaz `listDir` de todos os ancestrais já carregados; revalidar só o alvo (review rodada 2).
- [ ] `frontend/src/state/notebookTree.ts:120` — falha transitória numa revalidação zera `entries` da pasta já listada; preservar as entradas anteriores no `catch` (review rodada 2).
- [ ] `frontend/src/components/files/NotebookTree.tsx` — nome sugerido do rascunho de New folder calculado antes da 1ª listagem pode colidir; renderizar só com status `ready` (review rodada 2).
- [ ] `frontend/src/components/files/NotebookTree.tsx:213` — `nav.findIndex` dentro do `rows.map` é O(n²) por render; montar `Map<key, index>` uma vez (review rodada 3).

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- #1 resolvido (Esc só na árvore)
- #8 resolvido (falha mantém entries); docstrings de :52/:61 alinhadas
