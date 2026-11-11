# Pendências (nits) — libs-por-ambiente-spark

Origem: code review rodada 1 (2026-11-09 13:16:53 -0300), baseline ba854ce.

- [ ] `backend/src/notisbook/api/spark.py:95` — campo do 422 escolhido por prefixo da mensagem; validar nome e spec em try separados (remove a 2ª chamada a validate_name em :98).
- [ ] `backend/src/notisbook/api/spark.py:186` — 409 do remove diz "Install … in progress"; usar "Another job for Spark {version} is in progress".
- [ ] `backend/src/notisbook/spark/installer.py:209,244` — find()/discover() faz I/O síncrono no event loop; comentar o trade-off (sem await entre check e lock).
- [ ] `backend/src/notisbook/spark/packages.py:62,67` — stderr do `uv pip list` descartado; logar últimas linhas com log.warning.
- [ ] `frontend/src/components/spark/PackagesDialog.tsx:67` — `const locked = busy;` alias redundante.
- [ ] `frontend/src/components/spark/AddLibraryDialog.tsx:76` — erro não-422 exibido duas vezes (Add e pai).

Origem: code review rodada 4 (pós-teste do operador), baseline ba854ce.

- [ ] `backend/src/notisbook/api/spark.py:279,289` — `_pins` lista o env antes de checar sessão/lock; pré-checar `has_session`/`is_mutating` para devolver 409 em vez de 500 "Cannot pin core libraries".
- [ ] `backend/src/notisbook/api/spark.py:242` — docstring de `_pins` imprecisa; `:243-246` duplicam `installer.find`/`shutil.which`.
- [ ] `frontend/src/components/spark/Spark.module.css:515` — coluna de versão sem `font-variant-numeric: tabular-nums` após troca para fonte sans.

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- L2 resolvido (texto do 409)
- L5 já estava resolvido
- L7 resolvido (409 antes de _pins)
- L8 parcial: docstring de _pins alinhada; busca duplicada segue pendente
