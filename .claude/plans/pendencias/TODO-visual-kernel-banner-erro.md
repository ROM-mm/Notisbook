# Pendências (nits do code review) — visual-kernel-banner-erro

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/components/kernel/Kernel.module.css:104` — sombra `4px 4px 0 var(--color-danger-subtle)` é translúcida e quase some sobre o pontilhado; criar token opaco `--danger-shadow` por tema (padrão de `--btn-shadow`).
- [ ] `frontend/src/components/kernel/Kernel.module.css:111` — "!" gerado por CSS é anunciado por leitor de tela dentro de `role="alert"`; usar `content: "!" / "";`.
- [ ] `frontend/src/components/kernel/Kernel.module.css:120` — `var(--font-weight-bold, 700)` cita token inexistente; usar `--font-weight-semibold` ou `700`.
- [ ] `frontend/src/components/notebook/Notebook.module.css:77` — `.banner` de erro ao salvar (NotebookView, `role="alert"`) ficou no visual antigo, logo abaixo do banner do kernel.
- [ ] `frontend/src/components/kernel/Kernel.module.css:129` — palavra longa sem quebra (URL, caminho, id) ainda pode estourar o cartão; adicionar `overflow-wrap: anywhere` em `.banner > span` (review rodada 2).
