# Pendências (nits do code review) — visual-environments-dialogos

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/styles/tokens.css:94,143,188` — `--btn-shadow` repete os valores de `--cell-shadow` nos três temas; declarar `--btn-shadow: var(--cell-shadow)` uma vez no `:root` claro.
- [ ] `frontend/src/styles/dialog.module.css:93-100` — `.neo :global(.input):focus` duplica o foco global e `.neo :global(.input)` só atinge o input da InstallPanel; enxugar ou fazer o `.input` de Spark herdar do escopo (review rodada 2).
- [ ] Raios `16px` / `14px 14px 0 0` literais em 4 lugares (Notebook, `.block`, `.job`, `.dialog`); criar `--card-radius` e `--card-radius-inner` em tokens.css (review rodada 2).
