# Pendências (nits do code review) — visual-celulas-cartao

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/components/notebook/Notebook.module.css:158,183` — raios `16px` e `14px 14px 0 0` literais; criar `--cell-radius`/`--cell-border-width` e usar `calc()` no cabeçalho.
- [ ] `frontend/src/components/notebook/Notebook.module.css:2-3` — comentário de topo ainda descreve "borda sutil e fundo levemente acinzentado".
- [ ] `frontend/src/components/notebook/Notebook.module.css:307` — comentário do `.codeBox` ("campo branco simples") descreve o quê e fica incorreto no tema escuro.
- [ ] `frontend/src/components/notebook/Notebook.module.css:165` — comentário de `.cellActive` atribui a herança da sombra à ordem de declaração; o motivo real é que `editMode` implica `active` (review rodada 2).
