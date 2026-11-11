# Pendências (nits do code review) — ajustes-ui-paineis-topbar

Origem: code review rodada 1, 2026-11-09. Não reimplementados neste plano.

- [ ] `frontend/src/App.tsx:41` — polling de recursos roda desde o boot mesmo sem notebook aberto (widget não renderizado) ou com widget oculto (<1280px). Sugestão: start/stop por refcount na montagem de `SystemResources`.
- [ ] `frontend/src/components/shell/SystemResources.tsx:19` — RAM em base 1024 rotulada "GB" e disco em base 1000: unidades mistas (decisão D4 do plano; avaliar rótulo "GiB").
- [ ] `frontend/src/components/shell/ResizeHandle.tsx:19` — coordenada inicial do drag em `useState`; usar `useRef`.
- [ ] `frontend/src/components/shell/ResizeHandle.tsx:43` — separator sem foco/teclado/aria-valuenow (fora de escopo por decisão do operador).
- [ ] `frontend/src/components/shell/AboutDialog.tsx` — borda de 1px herdada de `.dialog` ainda fecha o About ao clicar exatamente nela (review rodada 2; impacto desprezível).
- [ ] `frontend/src/components/shell/Topbar.tsx:159` — `>About</button>` com texto colado na tag; padrão do arquivo é texto em linha própria (review rodada 3).
