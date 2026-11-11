# Pendências (nits do code review) — correcoes-pendencias-alta

Origem: code review rodada 1, 2026-11-09. Não reimplementados neste plano.

- `backend/src/notisbook/notebooks/store.py:244` — `target.resolve()` fora do `try`: OSError raro vira 500 genérico em vez de mensagem; envolver em try/except com `exc.strerror`.
- `backend/src/notisbook/kernels/service.py:557-558` — `Settings()` criado duas vezes quando `home is None`; calcular uma vez.
- `backend/src/notisbook/api/jobs.py:55` — `asyncio.ensure_future` com coroutine; usar `asyncio.create_task`.
- `frontend/src/components/data/DirectoryPicker.tsx:60` — `onClick` inline multilinha fora do padrão; extrair `cancel()`.
- `frontend/src/state/variables.ts:258` — comentário descreve o quê; deixar só o porquê.

## Retirado do plano (decisão de produto pendente)
- `frontend/src/components/notebook/CellHeader.tsx:120` — seletor SQL aparece com qualquer kernel; o front não tem sinal de kernel com SQL (todo kernel listado é Spark, `language` sempre "python"). Exige campo novo no backend ou decisão de produto.
