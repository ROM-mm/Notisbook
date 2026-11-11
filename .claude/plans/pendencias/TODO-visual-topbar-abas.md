# Pendências (nits do code review) — visual-topbar-abas

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/components/shell/AppShell.module.css:165` — comentário da aba ativa atribui a cobertura da linha à altura; quem cobre é o alinhamento `flex-end` + fundo opaco.
- [ ] `frontend/src/components/shell/AppShell.module.css:142` — com scrollbar clássica (Windows/Linux) a barra do `overflow-x` aparece sobre a linha inset da faixa; avaliar `scrollbar-width: thin/none` ou documentar alvo macOS.
- [ ] `frontend/src/components/shell/AppShell.module.css:333` — `.topToggle[aria-pressed="true"]` não reage ao hover (mesma especificidade, declarado depois).
- [ ] `frontend/src/components/kernel/Kernel.module.css:197-211` — células ainda vazam nos cantos arredondados e na faixa da sombra `4px 4px 0` da toolbar sticky; avaliar wrapper sticky opaco (review rodada 2).
- [ ] `frontend/src/components/kernel/Kernel.module.css:226-230` — `.toolBtnPrimary` herda raio de 4px; os demais botões em cartão usam 8px (review rodada 2).
- [ ] `frontend/src/components/notebook/Notebook.module.css:143-145` — hover de `.addBtn` troca o fundo opaco por `--color-bg-hover` translúcido e o pontilhado aparece; sobrepor a tinta ao `--color-surface` (review rodada 3).
- [ ] `frontend/src/components/notebook/Notebook.module.css:134` — `border-radius: 999px` literal no lugar de `var(--radius-full)` (review rodada 3).
