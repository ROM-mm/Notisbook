# Avisos benignos do Spark suprimidos e erros do Spark curtos

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-06 16:32:44 -0300
Modificação: 2026-11-06 17:06:27 -0300
Finalização: 2026-11-06 17:06:27 -0300

## Objetivo

Separar dois casos:

- **Aviso de ação bem-sucedida:** some, a partir de uma lista curada. Entra o `WARN … version-hint.text` com 60 linhas de stack em toda tabela Iceberg nova.
- **Erro que impede a ação:** aparece curto e legível. Mostra o tipo, a classe do erro do Spark, a mensagem e a posição. O stack completo fica num "ver detalhes" recolhido.

O erro curto vale em células SQL e em células Python quando o erro vem do Spark. Erro de Python puro fica igual.

Por que esta abordagem:
- **Avisos no log4j, não no stream:** o log4j filtra o evento inteiro, incluindo o stack.
- **Erro encurtado só na tela:** o `.ipynb` grava o traceback intacto, porque o formato `error` do nbformat não aceita campos extras.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Backend: gerar `log4j2.properties` (default do Spark + filtros da lista curada) em `<env>/spark-conf/`; gravar na instalação de toda versão Spark; garantir (idempotente, atômico, só kernelspec gerenciado) no start do kernel | `python-engineer` | — | 1 | escrita |
| T2 | Frontend: parser puro de erro Spark (`sparkError.ts`); `ErrorOutput` com resumo + `<details>` "ver detalhes"; linguagem da célula chega ao `OutputArea` | `python-engineer` | — | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | `log4j2.properties` completo, que reproduz o default do Spark (console SYSTEM_ERR, padrão, root info, `repl` warn, loggers default) e acrescenta: `RegexFilter` DENY por mensagem em `org.apache.spark.util.Utils` (loopback, `SPARK_LOCAL_IP`) e em `org.apache.iceberg.hadoop.HadoopTableOperations` (version hint); `org.apache.hadoop.util.NativeCodeLoader` em error | O arquivo substitui o default inteiro. Filtrar por mensagem preserva os avisos úteis de `Utils` (ex.: porta do SparkUI). | `log4j2-defaults.properties` dos jars 3.5.9/4.3.0; `ipykernel/kernelapp.py:191,536` (stderr chega em blocos) | filtro de stream no backend (frágil); rebaixar `Utils` inteiro |
| D2 | Sem bump da revisão do bundle. O instalador grava o arquivo para toda versão, e o start do kernel garante o arquivo (regrava só se o conteúdo mudou). | O env 4.3.0 não tem `spark-conf/` e nunca fica `outdated`. Os envs atuais recebem a mudança sem reinstalar. | `installer.py:256-259`, `kernelspec.py:76,117-118`, `bundles.py:5` | subir a revisão (força reinstalação, não cobre 4.3.0) |
| D3 | Erro curto feito só no frontend, sobre `ename/evalue/traceback`. O `.ipynb` fica intacto. | O schema `error` tem `additionalProperties: false`. Reescrever no backend seria destrutivo. Na tela, funciona também em notebooks antigos e mantém o "ver detalhes" persistente. | schema nbformat v4.5 no `.venv`; `ErrorOutput.tsx:9-20` | handler no kernel (`_render_traceback_`, exige bootstrap e MIME novo); reescrita no backend |
| D4 | Erro do Spark = traceback com frame `/pyspark/` ou `/py4j/`, ou `ename` numa lista conhecida (`AnalysisException`, `ParseException`, `Py4JJavaError`, `IllegalArgumentException`, `StreamingQueryException`, `PythonException`, `SparkRuntimeException`, `PySpark*` …). Em célula SQL, todo erro vira resumo. | `ename` não traz o módulo; o frame é o sinal robusto | `py4j/protocol.py:470-477`; `pyspark/errors/exceptions/captured.py` 3.5.9/4.3.0 | só pelo `ename` |
| D5 | Resumo = `ename` + chip `[ERROR_CLASS]` + mensagem sem `JVM stacktrace` e sem plano lógico (até ~3 linhas/500 chars) + SQLSTATE e posição se existirem; em `Py4JJavaError`, a causa raiz (último `Caused by:`). Detalhe em `<details>` nativo, recolhido, com o traceback ANSI completo. | Escolha do operador: "ver detalhes" em vez de remover o stack | sem evidência — preferência do operador | remover o stack |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Gerador de log4j existe e é usado pelo instalador e pelo start | `grep -rn "render_log4j2\|write_log4j2" backend/src/notisbook/spark/ backend/src/notisbook/kernels/service.py` → definição + uso no instalador + uso no start (refinado na execução: o uso passa por `write_log4j2`, que chama `render_log4j2`) | feature |
| T1 | Envs existentes recebem o arquivo sem reinstalar | Após iniciar um kernel `spark430` e um `spark359`: `ls ~/spark-notebooks/envs/spark-4.3.0-*/spark-conf/log4j2.properties ~/spark-notebooks/envs/spark-3.5.9-*/spark-conf/log4j2.properties` → os dois existem | feature |
| T1 | Avisos da lista somem | Script avulso no scratchpad (fora do repo), com kernel real 3.5.9 e 4.3.0: criar uma SparkSession e `df.writeTo("iceberg.<ns>.<nova>").createOrReplace()` → `stream` stderr sem `version-hint`, `loopback`, `SPARK_LOCAL_IP` e `NativeCodeLoader` | feature |
| T1 | Avisos fora da lista continuam | Mesmo script: `spark._jvm.org.slf4j.LoggerFactory.getLogger("probe").warn("probe-x")` → stderr contém `probe-x` | constraint |
| T1 | INFO não volta | Mesmo script: stderr sem a linha ` INFO ` durante a criação da sessão e a escrita | constraint |
| T1 | Revisão do bundle inalterada | `git diff <baseline> -- backend/src/notisbook/spark/bundles.py \| grep -n "revision"` → sem mudança na constante de revisão | constraint |
| T1 | Loggers filtrados seguem `setLogLevel` (code review r1, minor) | `grep -nE '^logger\.[a-z0-9_]+\.name *= *org\.apache\.(spark\.util\.Utils\|iceberg\.hadoop\.HadoopTableOperations)' <saída de render_log4j2()>` → sem match (filtros no appender); script com kernel real: após `spark.sparkContext.setLogLevel("ERROR")`, `LoggerFactory.getLogger("org.apache.spark.util.Utils").warn("keep-utils-other")` não aparece, e sem `setLogLevel` aparece; avisos da lista seguem suprimidos e sem ` INFO ` | bugfix |
| T2 | Frontend compila | `npm --prefix frontend run typecheck && npm --prefix frontend run build` → exit 0 | constraint |
| T2 | Parser puro existe | `frontend/src/components/outputs/sparkError.ts` exporta a classificação e a extração (errorClass, SQLSTATE, posição, causa raiz); casos verificados por script avulso no scratchpad sobre tracebacks reais coletados em 3.5.9 e 4.3.0 | feature |
| T2 | Resumos corretos | Script avulso transpilando `sparkError.ts`, sobre os tracebacks reais de: SQL com tabela inexistente → `TABLE_OR_VIEW_NOT_FOUND` + posição; `df.select("nao_existe")` → resumo; `SELEC 1` → `ParseException` + posição; `spark._jvm.java.lang.Integer.parseInt("x")` → causa `NumberFormatException`; SQL sem sessão → resumo | feature |
| T2 | `Py4JJavaError` extrai classe/SQLSTATE/posição da exceção Java de topo (code review r1, minor) | script avulso sobre evalue Py4J com topo `org.apache.spark.SparkException: [FAILED_EXECUTE_UDF] ... SQLSTATE: 39000` → `errorClass == "FAILED_EXECUTE_UDF"` e `sqlState == "39000"`; sem exceção de topo, cai no cabeçalho | bugfix |
| T2 | Sem mensagem duplicada no resumo de `Py4JJavaError` sem `Caused by` (code review r2, minor) | script avulso: evalue Py4J com topo `org.apache.spark.sql.AnalysisException: [TABLE_OR_VIEW_NOT_FOUND] ...` e sem `Caused by:` → `rootCause` nulo ou com mensagem diferente de `message`; com `Caused by:`, `rootCause` segue preenchido | bugfix |
| T2 | Python puro inalterado | Mesmo script: traceback de `NameError` → classificado como não-Spark | constraint |
| T2 | "Ver detalhes" recolhido | `grep -n "<details" frontend/src/components/outputs/ErrorOutput.tsx` → match; teste manual: o erro mostra o resumo e o detalhe fechado | feature |
| T2 | `.ipynb` intacto | `git diff <baseline> -- backend/src/notisbook/kernels/ backend/src/notisbook/notebooks/` não altera o roteamento nem a gravação de `error`; teste manual: um notebook salvo com o erro tem `traceback` com o mesmo número de linhas exibido no detalhe | constraint |

## Arquivos previstos
- `backend/src/notisbook/spark/bundles.py` — T1
- `backend/src/notisbook/spark/installer.py` — T1
- `backend/src/notisbook/kernels/service.py` — T1
- `frontend/src/components/outputs/sparkError.ts` — T2
- `frontend/src/components/outputs/ErrorOutput.tsx` — T2
- `frontend/src/components/outputs/OutputArea.tsx` — T2
- `frontend/src/components/kernel/NotebookPage.tsx` — T2
- `frontend/src/components/notebook/Cell.tsx` — T2
- `frontend/src/components/outputs/Outputs.module.css` — T2 (registrado na execução: estilos do resumo; autorizado na delegação)

## Fora de escopo
- Esconder o lambda gerado da célula SQL no detalhe — melhoria opcional.
- Alterar `spark.sql.pyspark.jvmStacktrace.enabled`.
- Filtro de stream no backend para texto impresso direto em `System.err` fora do log4j — reserva futura.
- **Documentação de produto** — nenhuma.

## Não mexer
- Formato das saídas `error` gravadas no `.ipynb` (`ename/evalue/traceback` intactos)
- `spark-defaults.conf` gerado e a constante de revisão do bundle
- Renderização de erros de Python puro

## Status
- [x] T1 (801b8fc + fe783dc)  - [x] T2 (08c2ea1 + fe783dc + ea2b8bf)

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | bug-engineer | FAILED | 73792 | 32328 |
| 0 | knowledge-engineer | OK | 78286 | 39333 |
| 0 | software-architect | OK | 184525 | 53699 |
| 1 | python-engineer | OK | 129320 | 62375 |
| 2 | python-engineer | OK | 120740 | 59771 |
| 2 | general-purpose (code-review) | OK | 122063 | 74119 |
| 2 | plan-auditor | OK | 52555 | 35615 |
| 2 | python-engineer (code review r1) | OK | 100793 | 48407 |
| 2 | general-purpose (code-review r2) | OK | 85448 | 68780 |
| 2 | plan-auditor (r2) | OK | 61190 | 34068 |
| 2 | python-engineer (code review r2) | OK | 29865 | 34268 |
| 2 | general-purpose (code-review r3) | OK | 40929 | 60357 |
| 2 | plan-auditor (r3) | OK | 48214 | 34194 |
| — | memory-manager | OK | 15712 | 39043 |
<!-- effort-ledger:end -->
