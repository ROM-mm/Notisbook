# Spark SQL (rename) + célula DuckDB SQL

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-07 22:40:29 -0300
Modificação: 2026-11-08 01:24:50 -0300
Finalização: 2026-11-08 01:24:50 -0300

## Objetivo

Seletor de linguagem da célula passa a ser **Python | Spark SQL | DuckDB SQL**. "SQL" vira só rótulo "Spark SQL" (valor `"sql"` no `.ipynb` intacto). A célula DuckDB SQL executa UMA instrução SQL no próprio kernel e exibe o resultado na mesma grade HTML. Escolhido em vez de kernel separado porque reaproveita o padrão vigente: tradução no backend, query como literal JSON, renderer oculto no kernel. Operador descartou Trino, Scala e R nesta rodada.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Rótulo "SQL" → "Spark SQL" no seletor | python-engineer | — | 1 | escrita |
| T2 | `duckdb==<versão fixa>` no instalador base do ambiente + import no `_validate` | python-engineer | T1 | 2 | escrita |
| T3 | Backend: `"duckdb"` no protocolo, despacho por engine, `run_duckdb`/`_build_duckdb` sobre a grade genérica, `STATE` preservado na troca de versão do módulo, mensagem de reinstalação sem duckdb | python-engineer | T2 | 3 | escrita |
| T4 | Frontend: `CellLanguage` com `"duckdb"`, família de linguagem nas marcas de troca, envio de `language`, placeholder, editor SQL, rótulo/ordem do seletor; erro DuckDB sem resumo Spark | python-engineer | T3 | 4 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3
- Wave 4 (serial, escrita): T4 — backend antes do frontend (D6)

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Valor `"duckdb"` em `metadata.notisbook.language`; Spark segue `"sql"`, Python sem chave | Notebooks salvos abrem sem migração | `frontend/src/state/notebook.ts:216-219`; parecer software-architect | renomear `"sql"` para `"spark_sql"` (quebra notebooks salvos) |
| D2 | Conexão DuckDB in-memory, lazy, uma por kernel, guardada no módulo oculto; persistir = `ATTACH` explícito | Evita lock de arquivo entre kernels e arquivos órfãos; segue semântica de temp view | parecer software-architect (lock: unverified) | arquivo único em `~/.notisbook` (lock); arquivo por notebook (órfãos, mapeamento) |
| D3 | `duckdb` com versão fixada no instalador base, não em `Bundle.pip` | Cobre todas as versões Spark, inclusive sem bundle | `backend/src/notisbook/spark/installer.py:157`; `spark/bundles.py:44-49` | `Bundle.pip` (cobertura parcial, mistura com revisão de JARs) |
| D4 | Extensões fora; conexão com autoinstall desligado e `extension_directory` sob `NOTISBOOK_HOME/duckdb/extensions` (caminho vindo do backend) | Kernel sobe offline; escrita só na raiz única | parecer software-architect (nomes de opção: unverified) | pré-instalar iceberg/delta/httpfs (binários por plataforma, peso) |
| D5 | Marcas de troca por família (`python` × `sql`), marcas atuais `-- [py] ` / `# [sql] `; Spark SQL ↔ DuckDB SQL não comenta, só limpa outputs | Compatível com notebooks salvos; mesma família não precisa comentar | `frontend/src/state/notebook.ts:226-249` | marcas por dialeto (quebra compatibilidade) |
| D6 | Deploy backend antes do frontend | Valor fora do `Literal` é rejeitado com `bad_message` | `backend/src/notisbook/kernels/protocol.py:24`; `api/sessions.py:108-110` | — |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Seletor exibe "Spark SQL" | `grep -rn 'sql: "SQL"' frontend/src` → sem ocorrência; `grep -n 'sql: "Spark SQL"' frontend/src/components/notebook/CellHeader.tsx` → 1 ocorrência | feature |
| T1 | Notebook antigo com `"language": "sql"` abre como Spark SQL e executa | teste manual: abrir notebook existente com célula SQL, rodar, grade aparece | constraint |
| T1 | Typecheck limpo | `cd frontend && npx tsc --noEmit` → exit 0 | constraint |
| T2 | Versão do duckdb fixada no instalador base | `grep -n 'duckdb==' backend/src/notisbook/spark/installer.py` → ≥1 ocorrência; `grep -n duckdb backend/src/notisbook/spark/bundles.py` → sem ocorrência | feature |
| T2 | Ambiente instalado importa a versão fixada | após instalar uma versão: `<env>/bin/python -I -c "import duckdb; print(duckdb.__version__)"` → imprime a versão fixada | feature |
| T2 | Extensões embutidas conferidas (fecha unverified de D4) | `<env>/bin/python -I -c "import duckdb; print(duckdb.sql(\"select extension_name from duckdb_extensions() where installed\").fetchall())"` → lista registrada no retorno | constraint |
| T3 | Protocolo e serviço aceitam `"duckdb"` | `grep -n '"duckdb"' backend/src/notisbook/kernels/protocol.py backend/src/notisbook/kernels/service.py` → ≥1 em cada | feature |
| T3 | Grade DuckDB: colunas duplicadas, numérico à direita, null em itálico | teste manual: `select 1 as a, 'x' as a, 1.5::decimal(10,2) d, date '2024-01-01' dt, null n` | feature |
| T3 | Limites de linhas e caracteres respeitados | teste manual: `select range from range(5000)` → rodapé de 1000 linhas; `select repeat('x', 2000)` → valor cortado | feature |
| T3 | Instrução sem resultado mostra "OK" e estado persiste no kernel | teste manual: `create table t(i int)` → "OK"; célula seguinte `select * from t` → grade vazia | feature |
| T3 | Restart zera o estado DuckDB | teste manual: após restart, `select * from t` → erro de catálogo | constraint |
| T3 | DuckDB roda sem SparkSession ativa | teste manual: kernel recém-iniciado, célula DuckDB `select 42` → grade | feature |
| T3 | Ambiente sem duckdb mostra mensagem de reinstalação | teste manual em ambiente antigo: célula DuckDB → erro com texto "reinstall" | feature |
| T3 | Sem rede, leitura remota falha sem travar | teste manual offline: `select * from read_csv('https://example.com/x.csv')` → erro em segundos, kernel idle | constraint |
| T3 | Spark SQL e Python sem regressão | teste manual: célula Spark SQL `select 1` → grade; célula Python `print(1)` → `1` | constraint |
| T3 | Célula DuckDB só com comentário não estoura `IndexError` (review r1, `sql_cell.py:164`) | leitura de `run_duckdb`: guarda para `extract_statements` vazio; teste no venv descartável com `-- nada` → mensagem clara ou "OK", sem `IndexError` | bugfix |
| T3 | `DUCKDB_STATUS_STATEMENTS` alinhado ao enum do duckdb 2.0.0 (review r1, `sql_cell.py:44-47`) | `grep -n COMMENT_ON backend/src/notisbook/kernels/sql_cell.py` → sem ocorrência; `grep -nE 'MERGE_INTO|COPY_DATABASE|EXPORT' backend/src/notisbook/kernels/sql_cell.py` → 3 nomes presentes | bugfix |
| T3 | Pasta de extensões derivada do `settings.home` injetado, não de `default_home()` (review r1, `service.py:381`) | `grep -n default_home backend/src/notisbook/kernels/service.py` → sem ocorrência; `app.py` passa o home ao `KernelService` | refactor |
| T4 | Frontend reconhece `"duckdb"` | `grep -n '"duckdb"' frontend/src/state/notebook.ts` → ≥1; `npx tsc --noEmit` → exit 0 | feature |
| T4 | Resumo de erro Spark só para Spark SQL | `grep -rn '=== "sql"' frontend/src` → só em `OutputArea.tsx`; teste manual: erro de sintaxe DuckDB → traceback comum, erro Spark SQL → resumo Spark | constraint |
| T4 | Trocas de linguagem com marcas por família | teste manual: Python→DuckDB comenta com `-- [py] `; DuckDB→Spark SQL não altera fonte e limpa outputs; Spark SQL→Python comenta com `# [sql] `; notebook salvo com marcas antigas volta sem perda | feature |
| T4 | Seletor na ordem Python, Spark SQL, DuckDB SQL e `.ipynb` grava o valor | teste manual: menu nessa ordem; salvar e `grep '"language": "duckdb"' <notebook>.ipynb` → ≥1 | feature |

## Arquivos previstos
- `frontend/src/components/notebook/CellHeader.tsx` — T1, T4
- `backend/src/notisbook/spark/installer.py` — T2
- `backend/src/notisbook/kernels/protocol.py` — T3
- `backend/src/notisbook/kernels/service.py` — T3
- `backend/src/notisbook/kernels/sql_cell.py` — T3
- `backend/src/notisbook/app.py` — T3 (ampliação de escopo: review r1, injeção do home)
- `frontend/src/state/notebook.ts` — T4
- `frontend/src/state/kernel.ts` — T4
- `frontend/src/components/notebook/Cell.tsx` — T4
- `frontend/src/components/notebook/CodeEditor.tsx` — T4
- `frontend/src/components/outputs/OutputArea.tsx` — T4
- `frontend/src/ws/protocol.ts` — T4
- `frontend/src/ws/session.ts` — T4

## Fora de escopo
- Painel Variables reconhecer objetos DuckDB (`kernels/introspect.py`) — fora do pedido.
- DuckDB lendo catálogos Iceberg/Delta/Spark e troca de dados Spark ↔ DuckDB — operador limitou a "apenas nível SQL".
- Extensões DuckDB pré-instaladas, arquivo DuckDB persistente, autocomplete de dialeto — ver D2/D4.
- Selo `outdated` para ambientes sem duckdb — sinalização só por mensagem em runtime.
- Trino, Scala, R — descartados pelo operador nesta rodada.
- **Documentação de produto** — nenhuma identificada como desatualizada (docstring de `sql_cell.py` é código e é atualizada em T3). Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- `backend/src/notisbook/spark/bundles.py` — matriz de JARs e `Bundle.pip`.
- Valor `"sql"` no metadata e marcas `-- [py] ` / `# [sql] ` existentes.
- Caminho Spark SQL: `SparkSession.getActiveSession()`, nunca `getOrCreate`; query como literal JSON, nunca interpolada.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 81712 | 56662 |
| 0 | software-architect | OK | 170286 | 51472 |
| 1-4 | python-engineer | OK | 129611 | 82753 |
| review-r1 | code-review | OK | 151829 | 80206 |
| audit-r1 | plan-auditor | OK | 34458 | 30756 |
| fix-r1 | python-engineer | OK | 35504 | 35951 |
| review-r2 | code-review | OK | 71295 | 69418 |
| audit-r2 | plan-auditor | OK | 40241 | 30704 |
| pós-validação | memory-manager | OK | 19873 | 48373 |
<!-- effort-ledger:end -->
