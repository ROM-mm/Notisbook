# Pendências cosméticas — bundle Delta/Iceberg/Hudi

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06
Modificação: 2026-11-06
Finalização: —

## Objetivo

Resolver os nits do code review do plano `20261105_main_spark-bundle-lakehouse.md`, que não bloquearam o commit.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| N1 | `backend/src/notisbook/spark/installer.py:246` — `http.client.IncompleteRead`/`HTTPException` escapam do `except OSError` de `_install_bundle`; o job mostra "unexpected error" em vez de "cannot download <jar>" | python-engineer | — | 1 | escrita |
| N2 | `backend/src/notisbook/api/spark.py:84` — checagem de sessão ativa duplicada com a do `remove_version`; extrair helper `_ensure_no_session` | python-engineer | — | 1 | escrita |
| N3 | `backend/src/notisbook/spark/installer.py:160` — comentário contraditório ("cannot be cancelled" / "stops at the next chunk"); reescrever como "the download thread only notices cancellation between chunks" | python-engineer | — | 1 | escrita |
| N4 | `backend/src/notisbook/spark/bundles.py:125` — docstring de `render_spark_defaults` não registra que o Hudi fica sem `HoodieCatalog` (DDL Hudi via SQL limitado no catálogo de sessão) | python-engineer | — | 1 | escrita |
| N5 | `backend/src/notisbook/spark/installer.py:164` — exceção da task de download nunca é lida após o `asyncio.wait` ("Task exception was never retrieved") | python-engineer | — | 1 | escrita |
| N6 | `backend/src/notisbook/spark/installer.py:302-308` — env anterior mantido por sessão ativa fica órfão; warning deve dizer que sai na próxima instalação (ou limpeza oportunista) | python-engineer | — | 1 | escrita |
| N7 | `backend/src/notisbook/spark/installer.py:285` — smoke sobe JVM sem timeout; envolver em `asyncio.wait_for(..., SMOKE_TIMEOUT)` | python-engineer | — | 1 | escrita |
| N8 | `backend/src/notisbook/kernels/service.py:463` — comentário em inglês com a palavra "arranque"; trocar por "startup" | python-engineer | — | 1 | escrita |
| N9 | `backend/src/notisbook/spark/installer.py:309` — com sessão ativa o `_cleanup` sai cedo e também preserva dirs órfãos `spark-<v>-????????`; preservar só os envs do kernelspec anterior | python-engineer | — | 1 | escrita |
| N10 | `backend/src/notisbook/spark/bundles.py:54` — chave do `MATRIX` repete `Bundle.key`; montar `{b.key: b for b in (...)}` | python-engineer | — | 1 | escrita |
| N11 | `backend/src/notisbook/spark/installer.py:73` — chaves checadas pelo `SMOKE_SCRIPT` duplicam as de `render_spark_defaults`; exportar constante de `bundles.py` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N1, N2, N3, N4, N5, N6, N7, N8, N9, N10, N11

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| N1 | Falha HTTP de download é reportada como erro de download | `grep -n "HTTPException" backend/src/notisbook/spark/installer.py` → presente no `except` de `_install_bundle` | feature |
| N2 | Checagem de sessão ativa em um helper só (`api/spark.py:84`, `:98`, `app.py:41`) | `grep -rn 'session\["kernel_name"\] ==' backend/src/notisbook/api/spark.py backend/src/notisbook/app.py` → nenhuma ocorrência (helper único) | feature |
| N3 | Comentário coerente | `grep -n "cannot be cancelled" backend/src/notisbook/spark/installer.py` → nenhuma ocorrência | feature |
| N4 | Docstring registra limitação do Hudi | `grep -n "HoodieCatalog" backend/src/notisbook/spark/bundles.py` → presente | feature |
| N5 | Exceção da task de download consumida | `grep -nE "download.exception\(\)|add_done_callback" backend/src/notisbook/spark/installer.py` → presente | feature |
| N6 | Warning do env mantido explica quando ele sai | `grep -n "next install" backend/src/notisbook/spark/installer.py` → presente no warning do `_cleanup` | feature |
| N7 | Smoke com timeout | `grep -n "SMOKE_TIMEOUT" backend/src/notisbook/spark/installer.py` → definido e usado em `wait_for` | feature |
| N8 | Comentário só em inglês | `grep -n "arranque" backend/src/notisbook/kernels/service.py` → nenhuma ocorrência | feature |
| N9 | Órfãos removidos mesmo com sessão ativa | `grep -n "previous" backend/src/notisbook/spark/installer.py` → `_cleanup` preserva só os envs anteriores referenciados | feature |
| N10 | Chave única por entrada | `grep -nE '^    "[0-9.-]+": Bundle' backend/src/notisbook/spark/bundles.py` → nenhuma ocorrência | feature |
| N11 | Chaves do smoke vêm de `bundles.py` | `grep -n "CLASS_KEYS" backend/src/notisbook/spark/bundles.py backend/src/notisbook/spark/installer.py` → definida e usada | feature |

## Arquivos previstos
- `backend/src/notisbook/spark/installer.py` — N1, N3, N5, N6, N7, N8, N9, N10, N11
- `backend/src/notisbook/api/spark.py` — N2
- `backend/src/notisbook/app.py` — N2
- `backend/src/notisbook/kernels/service.py` — N8
- `backend/src/notisbook/spark/bundles.py` — N4, N10, N11

## Fora de escopo
- Qualquer mudança de comportamento além das listadas acima.
- **Documentação de produto** — nenhuma afetada.

## Não mexer
- Contrato da API e comportamento atômico do instalador.

## Status
- [ ] N1  - [ ] N2  - [ ] N3  - [ ] N4  - [ ] N5  - [ ] N6  - [ ] N7  - [ ] N8  - [ ] N9  - [ ] N10  - [ ] N11

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- N1 resolvido (HTTPException/IncompleteRead)
- N2 já estava resolvido (has_session)
- N5 provável falso positivo (asyncio.shield)
- N6 e N9 resolvidos (cleanup com sessão ativa)
- N7 resolvido (timeout no smoke)
