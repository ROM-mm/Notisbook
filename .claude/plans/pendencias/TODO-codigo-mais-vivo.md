# Pendências (nits) — codigo-mais-vivo

Origem: code review rodada 1, 2026-11-11.

- [ ] `frontend/src/components/notebook/Notebook.module.css:8` — comentário diz que a paleta anda junto com `backend/.../html_report.py:89-90`; o export segue com paleta antiga (export HTML adiado pelo operador).
- [ ] `frontend/src/styles/tokens.css:114` — dourado claro `#a8761a` ≈ 3,98:1 sobre `#fff` (abaixo de WCAG AA 4,5:1; sugestão `#8a6114`); comentário escuro `#6a9955` ≈ 3,6:1 sobre `#35343c`.
- [ ] `frontend/src/components/notebook/Notebook.module.css:20` — `--syntax-property` neutro vale para todas as linguagens (Python `obj.attr` perde cor) — alinhado ao padrão Databricks pedido; confirmar com o operador.
- [ ] `frontend/src/components/notebook/editorTheme.ts:20-21` — `fontVariantLigatures: "contextual"` e `fontFeatureSettings: '"calt" 1'` redundantes.

Origem: code review rodada 2, 2026-11-11.

- [ ] `frontend/src/components/notebook/editorTheme.ts:75` — `QUALIFIER_TAIL` não cobre `t.*` (alias antes de `*` não fica dourado); sugestão `/^\.[\w"`*]/`.
- [ ] `frontend/src/components/notebook/editorTheme.ts:63` — `t.emphasis` itálico em markdown vira oblíquo sintético (Fira Code sem itálico).

Origem: code review rodada 3, 2026-11-11.

- [ ] `frontend/src/styles/tokens.css:114` — no claro, `--sx-fn`, `--sx-type` e `--sx-qual` compartilham `#a8761a` (no escuro fn ≠ type/qual); se quiser hierarquia igual, dar a `--sx-fn` tom próprio (ex.: `#795e26`).
