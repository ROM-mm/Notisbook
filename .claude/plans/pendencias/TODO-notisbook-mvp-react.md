# Pendências cosméticas — Notisbook MVP

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-05 09:55:24 -0300
Modificação: 2026-11-05 10:32:59 -0300
Finalização: —

## Objetivo

Achados `nit` do code review do plano `20261105_main_notisbook-mvp-react` (rodada 1), fora do gatilho do loop. Retomada a critério do operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| N1 | `frontend/src/state/kernel.ts:1-25` e `frontend/src/state/notebook.ts:1-23`: docstring de módulo > 15 linhas | general-purpose | — | 1 | escrita |
| N2 | `backend/src/notisbook/spark/prereqs.py:80`: `resolve_java_home` ignora `_java_home_tool()` | python-engineer | — | 1 | escrita |
| N3 | `backend/src/notisbook/__main__.py:29`: access log do uvicorn grava `token=` | python-engineer | — | 1 | escrita |
| N4 | `backend/src/notisbook/api/jobs.py:43`: WS de job não detecta desconexão até o próximo evento | python-engineer | — | 1 | escrita |
| N5 | `backend/src/notisbook/static.py:47`: estáticos fora de `/assets` sem header CSP | python-engineer | — | 1 | escrita |
| N7 | `frontend/src/state/kernel.ts:234-238`: `pump` limpa saídas antes de confirmar o envio do execute (rodada 2) | general-purpose | — | 1 | escrita |
| N6 | `start.sh:34`: `npm ci` só roda se `node_modules` não existe | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N2 → N3 → N4 → N5 → N6 → N1 → N7

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| N1 | Docstrings ≤ 15 linhas | primeira docstring/comentário de bloco de cada arquivo com ≤ 15 linhas (`sed -n 1,20p`) | refactor |
| N2 | prereqs usa o seam | `grep -n "_java_home_tool()" backend/src/notisbook/spark/prereqs.py` inclui a função `resolve_java_home` | refactor |
| N3 | Token fora do access log | após `curl "127.0.0.1:<p>/api/health?token=X"`, `grep -c "token=X" <log do servidor>` → 0 | feature |
| N4 | Desconexão detectada | fechar o WS de um job ativo encerra o handler em ≤ 2 s (log/estado) | bugfix |
| N5 | CSP em todo HTML/estático | `curl -sI 127.0.0.1:<p>/favicon.svg` contém `content-security-policy` | feature |
| N7 | Saídas só limpas após envio | `grep -n -A3 'channel.execute' frontend/src/state/kernel.ts` mostra `clearOutputs` depois do retorno `true` | refactor |
| N6 | Deps atualizadas | tocar `frontend/package-lock.json` e rodar `./start.sh --no-browser` → log mostra `npm ci` | feature |

## Arquivos previstos
- `frontend/src/state/kernel.ts`, `frontend/src/state/notebook.ts` — N1
- `backend/src/notisbook/spark/prereqs.py` — N2
- `backend/src/notisbook/__main__.py` — N3
- `backend/src/notisbook/api/jobs.py` — N4
- `backend/src/notisbook/static.py` — N5
- `start.sh` — N6
- `frontend/src/state/kernel.ts` — N7

## Fora de escopo
- Qualquer mudança de comportamento além do apontado em cada nit.
- **Documentação de produto** — nenhuma.

## Não mexer
- Contratos REST/WS do plano principal.

## Status
- [ ] N1  - [ ] N2  - [ ] N3  - [ ] N4  - [ ] N5  - [ ] N6  - [ ] N7

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- N2 resolvido (resolve_java_home usa _java_home_tool)
- N3 resolvido (access log desligado)
- N4 resolvido (WS de jobs detecta desconexão)
