# Pendências (nits) — erros e avisos do Spark

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 16:51:45 -0300
Modificação: 2026-11-06 16:58:12 -0300
Finalização: —

## Objetivo

Nits do code review r1 do plano `20261106_main_erros-e-avisos-spark-concisos`, guardados para uma rodada futura. Não bloqueiam o commit.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `backend/src/notisbook/kernels/service.py:469-471` — regra de env gerenciado em helper único de `spark/kernelspec.py` (prefixo `spark-`, sob `base_dir`), usado também por `_ensure_log4j2` | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/spark/bundles.py:175-178` — comentário em até 3 linhas, nomeando o logger Hive que difere entre 3.5.9 e 4.3.0 | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/spark/bundles.py:223-224` — `NativeCodeLoader` também pelo `RegexFilter` do appender (sem logger declarado), ou comentário explicitando a exceção | python-engineer | — | 1 | escrita |
| T4 | `frontend/src/components/outputs/sparkError.ts:99` — não atribuir `rootCause` quando a causa tem a mesma classe e mensagem do topo | python-engineer | — | 1 | escrita |
| T5 | `frontend/src/components/outputs/sparkError.ts:72` — remover a guarda redundante `!line.startsWith("\t")` ou comentá-la | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Helper único | `grep -n "is_managed_conf_dir" backend/src/notisbook/spark/kernelspec.py backend/src/notisbook/kernels/service.py` → definição + uso | refactor |
| T2 | Comentário curto | leitura de `backend/src/notisbook/spark/bundles.py` acima de `render_log4j2`: ≤ 3 linhas | refactor |
| T3 | NativeCodeLoader coerente | `grep -n 'logger.nativecode' backend/src/notisbook/spark/bundles.py` → sem match, ou comentário que declara a exceção | refactor |
| T4 | Sem causa repetida em wrapper da mesma classe | script avulso com `Caused by:` de mesma classe/mensagem → `rootCause` nulo | bugfix |
| T5 | Guarda limpa | `grep -n 'startsWith("\\t")' frontend/src/components/outputs/sparkError.ts` → sem match, ou com comentário | refactor |

## Arquivos previstos
- `backend/src/notisbook/spark/kernelspec.py` — T1
- `backend/src/notisbook/kernels/service.py` — T1
- `backend/src/notisbook/spark/bundles.py` — T2, T3
- `frontend/src/components/outputs/sparkError.ts` — T4, T5

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Conteúdo gerado do `log4j2.properties`

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T1 resolvido (is_managed_env único)
- T4 não reproduzido: rootCause já é o Caused by mais profundo
