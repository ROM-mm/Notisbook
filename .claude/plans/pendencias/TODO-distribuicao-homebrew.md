# Pendências cosméticas — distribuição via Homebrew

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-11 01:09:28 -0300
Modificação: 2026-11-11 01:12:44 -0300
Finalização: —

## Objetivo

Nits do code review do plano `distribuicao-homebrew`, fora do gatilho do loop.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `.gitignore:1` — `backend/dist/` e `backend/src/notisbook/_frontend/` duplicam `backend/.gitignore:3-4`; manter só em `backend/.gitignore` | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/config.py:44` — em checkout sem `frontend/dist`, o dev cai no `_frontend` deixado pelo `build_release.py` e serve build antigo; apagar `_frontend` ao fim do script ou documentar | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Entradas só no `backend/.gitignore`, ainda ignoradas | `grep -c '_frontend' .gitignore` → 0; `git check-ignore backend/src/notisbook/_frontend/index.html` → exit 0 | constraint |
| T2 | Build de release não deixa `_frontend` velho para o dev | após `build_release.py`, `test -d backend/src/notisbook/_frontend` → exit 1 (ou decisão documentada) | constraint |

## Arquivos previstos
- `.gitignore` — T1
- `scripts/build_release.py` — T2

## Fora de escopo
- **Documentação de produto** — não alterada aqui.

## Não mexer
- `backend/.gitignore`

## Status
- [ ] T1  - [ ] T2

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
