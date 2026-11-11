# Pendências (nits do code review) — visual-painel-variables

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/components/variables/VariablesPanel.module.css:175,196` — `.more` e `.note` sem a margem/borda transparente de `.row`: "Show N more…" fica ~5.5px desalinhado e o hover não vira pílula.
- [ ] `frontend/src/components/variables/VariablesPanel.module.css:78,142` — `padding: 12px 16px 16px 12px` e `border-radius: 5px` literais; usar `--space-3`/`--space-4`.
- [ ] `frontend/src/components/variables/VariablesPanel.module.css:159-162` — `.type` segue `flex: none`; em painel estreito/nível profundo o nome some antes do tipo; dar ao `.type` `flex: 0 100 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis` (review rodada 2).
