# Pendências (nits do code review) — linha-codigo-saida

Origem: code review rodada 1, 2026-11-10. Não reimplementados neste plano.

- [ ] `frontend/src/components/notebook/Notebook.module.css:312` — espaço desigual em volta da linha (12px acima, ~20px abaixo: `padding-top` do `.outputBox` + `margin-top` do `.area`/`.preserved`); zerar o `padding-top` ou usar `.outputBox > :first-child { margin-top: 0 }`.
- [ ] `frontend/src/components/notebook/Cell.tsx:77` — `hasOutputs` usa `cell.outputs.length > 0`; saída só com `output_type` desconhecido (`.ipynb` vindo do disco) mostra a linha sobre área vazia.
