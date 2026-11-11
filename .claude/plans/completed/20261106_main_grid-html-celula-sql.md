# Célula SQL e DataFrame PySpark: resultado em tabela HTML

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-06 17:16:05 -0300
Modificação: 2026-11-06 17:46:43 -0300
Finalização: 2026-11-06 17:46:43 -0300

## Objetivo

Exibir o resultado da célula SQL como tabela estilo Databricks (cabeçalho, zebra, rodapé de contagem) em vez do ASCII do `show()` — só visual, sem nenhuma interação (sem ordenar, filtrar, copiar ou paginar). Opção C (HTML gerado no kernel) porque o frontend já renderiza `text/html` sanitizado (DOMPurify + Shadow DOM) com CSS de tabela: muda só backend, e o `.ipynb` abre como tabela também no Jupyter.

**Ampliação de escopo (2026-11-06 17:29, pedido do operador após testar T1):** a mesma grade para DataFrames PySpark em células Python, quando o DataFrame é a última expressão da célula (`df`) ou passado a `display(df)`. `df.show()` continua imprimindo texto (opção 1 escolhida pelo operador — substituir o `show()` ficou fora). O renderer vira um só, compartilhado entre SQL e Python, instalado no kernel por execute silencioso quando ele fica pronto (start e restart).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Trocar `show()` por `display` com tabela HTML + fallback `text/plain`, limite de linhas, corte de texto longo e tratamento de DDL sem colunas | python-engineer | — | 1 | escrita |
| T2 | Extrair o renderer para um módulo oculto do kernel (`render(df)` + `run(payload)`), instalado de forma idempotente por um snippet `ensure` executado em silêncio no `_await_ready` e no início de cada célula SQL | python-engineer | T1 | 3 | escrita |
| T3 | Registrar formatter IPython `text/html` por nome de tipo (lazy) para `pyspark.sql.dataframe.DataFrame` e `pyspark.sql.connect.dataframe.DataFrame`, usando o `render` compartilhado | python-engineer | T2 | 3 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 — concluída (commit 9a07c2d)
- Wave 3 (serial, escrita): T2, T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | HTML pronto gerado no kernel (opção C) | frontend já renderiza `text/html` sanitizado com CSS de tabela; zero mudança no front | `frontend/src/components/outputs/HtmlOutput.tsx:14-25`, `frontend/src/components/outputs/purify.ts:29-37` | B (mimetype próprio + componente React): mais arquivos, só se paga com interação, que o operador recusou; A (parse do ASCII no front): frágil com `\|`, multilinha e corte de 1 MB |
| D2 | `limit(1001).collect()` no lugar do `show()`, nunca ambos | os dois juntos executariam a query duas vezes | `backend/src/notisbook/kernels/sql_cell.py:22` | manter `show()` + `collect()`: custo dobrado e divergência em query não determinística |
| D3 | colunas renomeadas posicionalmente e `CAST AS STRING` antes do collect | evita erro com nomes duplicados e problema de serialização de data/decimal; `null` segue `None` | `sem evidência` — análise do knowledge-engineer | serializar tipos nativos: exige conversor por tipo |
| D4 | PySpark via formatter IPython registrado por nome (`for_type_by_name`), só `text/html` | cobre `df` e `display(df)` sem importar pyspark no registro; kernels sem Spark e pandas não são afetados; um único `collect` por exibição | `backend/src/notisbook/kernels/service.py:184-196`; análise do knowledge-engineer (comportamento IPython `unverified`) | substituir `DataFrame.show` (opção 2): quebra captura de stdout, `vertical`, loops — recusada pelo operador; `display` própria no namespace: sombreia a do IPython; `eagerEval` nativo: HTML diferente e limite 20 |
| D5 | instalação por execute silencioso no `_await_ready`, não no kernelspec | roda em start e restart sem regravar `kernel.json`; vale para qualquer kernel; célula SQL reexecuta o `ensure` idempotente, então não depende do startup | `backend/src/notisbook/kernels/service.py:154,184-196,410`; `backend/src/notisbook/spark/kernelspec.py:84` | `exec_lines` no argv do kernelspec: exige regravar specs instalados; `IPYTHONDIR`/`PYTHONSTARTUP`: globais ou dependem de arquivo |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `show()` removido | `grep -n "\.show(" backend/src/notisbook/kernels/sql_cell.py` → sem saída (exit 1) | feature |
| T1 | Saída via `display` com bundle `text/html` + `text/plain` | `grep -nE "text/html\|text/plain" backend/src/notisbook/kernels/sql_cell.py` → ambos presentes | feature |
| T1 | Nomes de coluna e valores escapados | `grep -n "html.escape" backend/src/notisbook/kernels/sql_cell.py` → presente | constraint |
| T1 | Máx. 1000 linhas; rodapé "mostrando as primeiras 1000 linhas" quando excede, senão "N linhas" | no app: `SELECT id FROM range(1500)` e `SELECT id FROM range(3)` → rodapés respectivos | feature |
| T1 | DDL sem colunas exibe "OK" em vez de `++ \|\| ++` | no app: `CREATE DATABASE IF NOT EXISTS vendas` → saída "OK" | bugfix |
| T1 | `null` visualmente distinto da string "null" | no app: `SELECT NULL AS a, 'null' AS b` → `a` estilizado (cinza/itálico), `b` texto normal | feature |
| T1 | Texto longo de célula truncado no kernel | no app: `SELECT repeat('x', 5000)` → valor cortado com `…` | constraint |
| T1 | Sem SparkSession ativa, mesma mensagem de erro | `grep -n "NO_SESSION_MESSAGE" backend/src/notisbook/kernels/sql_cell.py` → constante e uso presentes | constraint |
| T1 | Corte de texto longo aplicado no Spark antes do `collect()` (review rodada 1, minor `sql_cell.py:96`) | `grep -n "substring(" backend/src/notisbook/kernels/sql_cell.py` → presente no `selectExpr` | constraint |
| T1 | Módulo compila | `python3 -m py_compile backend/src/notisbook/kernels/sql_cell.py` → exit 0 | constraint |
| T2 | Renderer instalado como módulo oculto, sem poluir o namespace do usuário | `grep -n "_notisbook_display" backend/src/notisbook/kernels/sql_cell.py` → presente; no app: `dir()` numa célula Python não lista `render`/`run` | feature |
| T2 | Instalação silenciosa no kernel pronto (start e restart) | `grep -n "silent=True" backend/src/notisbook/kernels/service.py` → presente no caminho de `_await_ready` | feature |
| T2 | Grade SQL sem regressão | no app: `SELECT id FROM range(3)` → mesma grade com rodapé "3 linhas"; `CREATE DATABASE IF NOT EXISTS vendas` → "OK" | constraint |
| T2 | Kernel sem pyspark sobe sem erro | no app: kernel Python puro inicia em `idle` e `1+1` → `2` | constraint |
| T3 | Formatter registrado por nome para as duas classes de DataFrame | `grep -nE "for_type_by_name\|pyspark.sql.connect.dataframe" backend/src/notisbook/kernels/sql_cell.py` → presentes | feature |
| T3 | `df` como última expressão e `display(df)` mostram a grade | no app: `df = spark.range(3)` + `df` → grade com rodapé "3 linhas"; `display(spark.range(1500))` → rodapé "mostrando as primeiras 1000 linhas" | feature |
| T3 | `df.show()` inalterado | no app: `spark.range(3).show()` → tabela ASCII em texto, como antes | constraint |
| T3 | DataFrame pandas inalterado | no app: `import pandas as pd; pd.DataFrame({"a":[1]})` → tabela padrão do pandas | constraint |
| T3 | Re-registro do formatter substitui o já resolvido (review rodada 3, minor `sql_cell.py:126`) | `grep -n "for_type(" backend/src/notisbook/kernels/sql_cell.py` → presente em `register()` | bugfix |
| T2 | Falha da instalação silenciosa aparece no log do backend (review rodada 3, minor `service.py:224-225`) | leitura de `_install_display` em `service.py` → warning condicionado a verificação real (ex.: `user_expressions`) | bugfix |
| T2 | Célula SQL sem renderer instalado dá erro claro, não `KeyError` (review rodada 3, minor `sql_cell.py:182`) | `grep -n "KeyError\|não instalado" backend/src/notisbook/kernels/sql_cell.py` → mensagem clara presente | bugfix |
| T2 | Módulos compilam | `python3 -m py_compile backend/src/notisbook/kernels/sql_cell.py backend/src/notisbook/kernels/service.py` → exit 0 | constraint |

## Arquivos previstos
- `backend/src/notisbook/kernels/sql_cell.py` — T1, T2, T3
- `backend/src/notisbook/kernels/service.py` — T2

## Fora de escopo
- Ordenação, filtro, cópia, paginação ou qualquer interação na grade — operador pediu só visual.
- Mimetype próprio + componente React (opção B).
- Substituir `DataFrame.show()` pela grade (opção 2), `display` própria no namespace e `spark.sql.repl.eagerEval` — operador escolheu a opção 1.
- **Documentação de produto** — nenhuma.

## Não mexer
- Frontend inteiro (`frontend/**`).
- Frame WS `execute`, `cell.metadata.notisbook.language`, `backend/src/notisbook/kernels/protocol.py` e `backend/src/notisbook/spark/kernelspec.py`.
- `pyspark.sql.DataFrame.show` (sem monkeypatch).
- Nunca `getOrCreate()`; query sempre como literal JSON, sem interpolação.

## Status
- [x] T1 (9a07c2d)  - [x] T2 (851714f)  - [x] T3 (851714f)

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 95601 | 43315 |
| 1 | python-engineer | OK | 31188 | 32899 |
| 1 | code-review | OK | 58784 | 62275 |
| 1 | plan-auditor | OK | 23338 | 22015 |
| 2 | python-engineer | OK | 17141 | 29250 |
| 2 | code-review | OK | 49511 | 61821 |
| 2 | plan-auditor | OK | 34827 | 27191 |
| 3 | knowledge-engineer | OK | 158010 | 53771 |
| 3 | python-engineer | OK | 114124 | 66110 |
| 3 | code-review | OK | 118828 | 71788 |
| 3 | plan-auditor | OK | 35957 | 28850 |
| 4 | python-engineer | OK | 45931 | 43104 |
| 4 | code-review | OK | 55530 | 62914 |
| 4 | plan-auditor | OK | 34966 | 26328 |
<!-- effort-ledger:end -->
