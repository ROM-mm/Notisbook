# Painel de variáveis do kernel (Fase 1)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-06 23:47:42 -0300
Modificação: 2026-11-07 00:13:18 -0300
Finalização: 2026-11-07 00:13:18 -0300

## Objetivo

Painel à direita (abaixo do "Idle / Saved") que mostra as variáveis do kernel após cada execução, em árvore — "Special Variables" recolhido por padrão, detalhes de SparkSession/DataFrame/StructType — com botão de abrir/fechar no header e × no painel. Leitura por consulta silenciosa ao kernel no padrão do Catálogo, servida por REST novo; WS v1 não muda. Escolhido por ser seguro, não travar a próxima célula e reaproveitar cache/stale do Catálogo; protocolo de debug descartado (lê com célula rodando, desacelera execução). Mockup aprovado: painel 44px de cabeçalho alinhado ao "Notebooks", selo `after [n]`, ↻ e ×.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Backend: consulta de variáveis no kernel (resumo por tipo, limites, usuário × especiais, filhos por caminho JSON), fila/cache próprios sem gate de Spark, `GET /api/sessions/{id}/variables` e `.../variables/children` | python-engineer | — | 1 | escrita |
| T2 | Frontend: área direita no workspace, toggle no header, store ligado à sessão da aba (refresh no idle só com painel aberto + ↻), árvore com filhos sob demanda, selo stale, × | python-engineer | T1 | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Pull por execute silencioso no idle, reaproveitando `KernelSession.introspect` | Seguro, contrato WS intacto, stale com kernel ocupado já pronto | `backend/src/notisbook/kernels/service.py:367-430`; parecer do software-architect | comm (enfileira igual), debug protocol (race + lentidão), hook post_run_cell (custo em toda célula) |
| D2 | Fila e cache de variáveis separados do Catálogo | Varredura do Catálogo bloquearia o painel; `no_spark_session` limpa o cache inteiro | `service.py:380-382`, `service.py:425-426` | compartilhar a fila do Catálogo |
| D3 | Nada passa pelo formatador do IPython; resumo montado por tipo | Formatador HTML de DataFrame faz `collect` → job Spark | `backend/.../sql_cell.py:97` | `repr()` genérico |
| D4 | Área direita própria, independente do painel esquerdo; toggle no header | Pedido do operador + mockup | `frontend/src/state/workspace.ts:28,64` (só existe slot esquerdo) | toggle na barra do kernel |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Rotas de variáveis e filhos registradas | `grep -n "variables" backend/src/notisbook/api/variables.py backend/src/notisbook/app.py` → 2 rotas GET + include no app | feature |
| T1 | Consulta funciona sem SparkSession | função de variáveis em `backend/src/notisbook/kernels/introspect.py` sem retorno `no_spark_session` (grep no bloco de variáveis → vazio) | feature |
| T1 | Sem chamada que dispare job ou efeito colateral | `grep -nE "\.count\(|\.collect\(|toPandas|getattr\(" ` no bloco de variáveis de `introspect.py` → vazio | constraint |
| T1 | Fila/cache próprios | símbolo dedicado a variáveis (lock/cache) em `backend/src/notisbook/kernels/service.py` | feature |
| T2 | Painel com árvore, Special Variables e × | `grep -rn 'variables-panel\|variables-close\|variables-special' frontend/src/components/variables/` → 3 testids | feature |
| T2 | Toggle no header | `grep -n 'data-testid="toggle-variables"' frontend/src/components/shell/Topbar.tsx` → 1 | feature |
| T2 | Refresh no idle só com painel aberto + ↻ | `frontend/src/state/variables.ts` assina transição para `idle` condicionada ao painel aberto; testid `variables-refresh` presente | feature |
| T2 | Refresh no idle condicionado ao painel aberto vive no store (achado do plan-auditor) | `frontend/src/state/variables.ts` contém a assinatura da transição para `idle` e a condição de painel aberto; `VariablesPanel.tsx` sem `setTimeout`/debounce de refresh (grep → vazio) | refactor |
| T2 | `stale_path` não entra em laço de refresh (achado major do code review) | `stale_path` em `state/variables.ts` remove a chave e descendentes de `expanded`/`children` antes de reler; `load()` poda expandidos cujo `path[0]` sumiu de `data.variables` | bugfix |
| T2 | Refetch de filhos expandidos serializado ou com retry em `ok`+`stale` (achado minor) | `state/variables.ts`: fila de um por vez para refetch de filhos, ou reagendamento com backoff quando a resposta vem `stale: true` | bugfix |
| T1 | Slot/`__dict__` só lidos por descritor padrão, sem rodar property (achado minor) | `introspect.py` bloco de variáveis usa `types.MemberDescriptorType` para slots e `types.GetSetDescriptorType` para `__dict__`; `grep -n "object.__getattribute__(obj" ` no bloco → vazio | bugfix |
| T1 | Módulos exibem o nome (achado minor rodada 2) | `_odict` em `introspect.py` aceita `(types.GetSetDescriptorType, types.MemberDescriptorType)` para `__dict__` | bugfix |
| T2 | Filhos não ficam presos em "Loading…" após `load()` que não termina em ok (achado minor rodada 2) | `state/variables.ts`: `load()` zera `loading` dos filhos mantidos após `++generation`, ou o early-return por geração em `fetchChildren` aplica `loading: false` | bugfix |
| T1 | Backend compila | `python3 -m compileall -q backend/src` → exit 0 | constraint |
| T2 | Frontend compila | `cd frontend && npm run build` → exit 0 | constraint |

## Arquivos previstos
- `backend/src/notisbook/kernels/introspect.py` — T1
- `backend/src/notisbook/kernels/service.py` — T1
- `backend/src/notisbook/api/variables.py` — T1
- `backend/src/notisbook/app.py` — T1
- `frontend/src/api/types.ts` — T2
- `frontend/src/api/variables.ts` — T2
- `frontend/src/state/variables.ts` — T2
- `frontend/src/state/workspace.ts` — T2
- `frontend/src/components/variables/VariablesPanel.tsx` — T2
- `frontend/src/components/variables/VariablesPanel.module.css` — T2
- `frontend/src/components/shell/AppShell.tsx` — T2
- `frontend/src/components/shell/Topbar.tsx` — T2
- `frontend/src/components/shell/AppShell.module.css` — T2
- `frontend/src/components/shell/icons.tsx` — T2

## Fora de escopo
- "View" de valores longos, "Show Variables Size", barra de heap do driver — Fase 2.
- Push pelo kernel (comm/post_run_cell), psutil, painel redimensionável — Fase 3.
- **Documentação de produto** — nenhuma.

## Não mexer
- Protocolo WebSocket v1 (`backend/src/notisbook/kernels/protocol.py`).
- Comportamento do Catálogo (`api/catalog.py`, operações existentes em `introspect.py`).
- Formatador HTML de DataFrame (`sql_cell.py`).

## Status
- [x] T1  - [x] T2

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| - | software-architect | OK | 128531 | 55410 |
| 1 | python-engineer | OK | 299147 | 83776 |
| 2 | python-engineer | OK | 116266 | 68555 |
| - | plan-auditor | OK | 52457 | 31441 |
| - | code-review | OK | 178154 | 103107 |
| 1-2 | python-engineer | OK | 100952 | 52319 |
| - | plan-auditor | OK | 41999 | 31759 |
| - | code-review | OK | 155452 | 95342 |
| 1-2 | python-engineer | OK | 36035 | 34113 |
| - | plan-auditor | OK | 47734 | 33527 |
| - | code-review | OK | 257594 | 93373 |
| - | memory-manager | OK | 17312 | 45212 |
<!-- effort-ledger:end -->
