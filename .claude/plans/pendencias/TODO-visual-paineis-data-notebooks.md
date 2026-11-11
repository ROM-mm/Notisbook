# Pendências (nits do code review) — visual-paineis-data-notebooks

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/components/data/DataPanel.module.css:145` — `.tree { margin-inline }` nunca se aplica (perde para `.section > :not(.sectionHeader)`); ajustar o seletor ou apagar.
- [ ] `frontend/src/components/shell/ResizeHandle.tsx:36` — comentário "Linha de 1px no lugar da borda do painel" desatualizado para a variante "gap".
- [ ] `frontend/src/components/shell/Menu.module.css:111` — separador com `height: 1.5px` varia conforme o DPR; usar 1px ou 2px.
- [ ] `DataPanel.module.css:176-180` / `FileBrowser.module.css:128-132` — sombra da pílula de seleção cortada pelo `overflow: auto` do `.tree`; folga de 2px à direita e embaixo.
- [ ] `frontend/src/components/shell/ResizeHandle.tsx:10` — `GAP_HIT = 7` acoplado às margens de 7px de `DataPanel.module.css:35,39`; unificar numa custom property ou prop `hitReach` (review rodada 2).
- [ ] `frontend/src/components/data/DataPanel.module.css:1-4` — comentário com 4 linhas e impreciso ("divide por flex-grow"); reduzir para 3 linhas com o porquê (review rodada 2).
