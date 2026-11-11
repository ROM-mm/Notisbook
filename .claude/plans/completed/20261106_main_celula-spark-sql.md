# Célula com seletor Python | SQL (Spark SQL)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-06 15:26:15 -0300
Modificação: 2026-11-06 16:00:55 -0300
Finalização: 2026-11-06 16:00:55 -0300

## Objetivo

Permitir escolher, por célula, entre Python e SQL. Em SQL, a célula contém só a query. Ao executar, o backend roda `spark.sql(query)` na SparkSession ativa do kernel e devolve a grade do `show()` abaixo da célula. A linguagem é salva no `.ipynb`.

O caminho é deliberadamente simples, por decisão do operador: a saída é o texto do `show()`, há uma instrução por célula e o erro padrão do Spark é mantido. A grade tipada no estilo Databricks fica para depois e não quebra este contrato.

A exceção CSED para o frontend React/TS foi concedida. A T2 é delegada ao `python-engineer`, como nos planos anteriores do frontend.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Backend: campo `language` (`python`\|`sql`, default `python`) no frame `execute`; repassá-lo até `KernelSession.execute`; em `sql`, gerar código que roda `spark.sql(<query>).show(...)` na SparkSession ativa, com a query como literal JSON; sem sessão → mensagem clara | `python-engineer` | — | 1 | escrita |
| T2 | Frontend: seletor Python/SQL à esquerda, junto do botão de executar (remove o rótulo fixo da direita); `metadata.notisbook.language`; envio de `language` no `execute`; realce SQL no CodeMirror; troca com comentário marcado (A1); limpar saída ao trocar | `python-engineer` | T1 | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | O backend transforma SQL em código Python antes de `client.execute` | Contrato único; frame sem `language` segue como Python | `kernels/service.py:315-322`, `kernels/protocol.py:20-23` | Transformar no frontend; helper instalado no kernel (exigiria migrar envs) |
| D2 | Saída = texto do `df.show(1000, truncate=False)` | Simplicidade pedida pelo operador; o `show` já limita linhas e formata tipos | sem evidência — preferência do operador | mimetype `vnd.notisbook.table+json` com schema (adiado) |
| D3 | A query vai para o kernel como literal JSON, decodificado lá dentro; nunca interpolada | Aspas na query quebrariam o código; superfície de injeção | `kernels/introspect.py:195-199` (precedente) | f-string `spark.sql("...")` |
| D4 | Sessão obtida por `SparkSession.getActiveSession()`; ausente → erro "Nenhuma SparkSession ativa; crie uma numa célula Python" | `getOrCreate` automático subiria JVM com config default e ignoraria a config posterior do usuário | `kernels/introspect.py:26-28`; `spark/kernelspec.py:70-89` (kernel não cria `spark`) | `getOrCreate()` automático |
| D5 | Uma instrução por célula; erro padrão do Spark | Simplicidade pedida pelo operador | sem evidência — preferência do operador | separador léxico de `;`; erro reformatado |
| D6 | Sem magic `%sql` | O operador não quer digitar nada além da query; a linguagem vem do seletor | sem evidência — preferência do operador | `%sql` na primeira linha |
| D7 | Linguagem em `cell.metadata.notisbook.language` = `"sql"`; ausente = python (não gravar `"python"`) | Namespace evita colisão; metadata extra sobrevive ao round-trip e ao `nbformat.validate` | `state/notebook.ts:72-134`, `notebooks/store.py:65-80`, `spark/kernelspec.py:22` | `metadata.language` solto |
| D8 | Troca com conteúdo (A1): cada linha recebe o comentário da linguagem de destino com marca própria (`-- [py] ` em SQL, `# [sql] ` em Python); ao voltar, as linhas com a marca da troca anterior são descomentadas e as demais comentadas; célula vazia → só troca | Não perder código; não descomentar comentário escrito à mão | sem evidência — preferência do operador | (A2) desfazer só se a célula não foi editada |
| D9 | Trocar a linguagem apaga as saídas da célula | A saída deixa de corresponder ao conteúdo | sem evidência — preferência do operador | manter até a próxima execução |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Frame sem `language` vale `python` | `python -c` validando `{"v":1,"type":"execute","cell_id":"a","code":"x"}` pelo adapter de `kernels/protocol.py` → `language == "python"` | feature |
| T1 | `language` restrito a `python`\|`sql` | `grep -n 'language' backend/src/notisbook/kernels/protocol.py` mostra `Literal["python", "sql"]` com default `"python"`; frame com `"language":"r"` é rejeitado na validação | constraint |
| T1 | `language` chega à execução | `grep -n 'language' backend/src/notisbook/api/sessions.py backend/src/notisbook/kernels/service.py` mostra o repasse até `KernelSession.execute` | feature |
| T1 | Query nunca interpolada | `grep -n 'json.dumps' backend/src/notisbook/kernels/sql_cell.py` mostra a query serializada; `compile(build_code('SELECT "a" AS x, \'b\' AS y'), "<x>", "exec")` passa | constraint |
| T1 | SQL executa e mostra a grade | Kernel real com SparkSession ativa + frame WS avulso (script no scratchpad, fora do repo) com `language:"sql"`, `code:"SELECT 1 AS x"` → saída `stream` contendo `\|x  \|` e `\|1  \|` (o `show(truncate=False)` alinha à esquerda) | feature |
| T1 | Sem sessão → mensagem clara | Kernel sem SparkSession + frame `sql` → saída de erro contendo "Nenhuma SparkSession ativa" | feature |
| T1 | Python inalterado | Frame sem `language`, `code:"print(1)"` → `stream` `1` | constraint |
| T2 | Build do frontend passa | `cd frontend && npm run build` → exit 0 | constraint |
| T2 | Rótulo fixo removido | `grep -n 'code: "Python"' frontend/src/components/notebook/CellHeader.tsx` → sem match | feature |
| T2 | Linguagem persiste no `.ipynb` | Salvar notebook com célula SQL e rodar `python3 -c` com `json.load` → `cells[i]["metadata"]["notisbook"]["language"] == "sql"` | feature |
| T2 | `language` enviado no `execute` | `grep -n 'language' frontend/src/ws/protocol.ts frontend/src/state/kernel.ts` mostra o campo no frame e no envio | feature |
| T2 | Troca com comentário marcado | `grep -n '\[py\]\|\[sql\]' frontend/src/state/notebook.ts` mostra as marcas; teste manual: `x = 1` → SQL → `-- [py] x = 1`; acrescentar `SELECT 1` → Python → `x = 1` e `# [sql] SELECT 1`; `# meu comentário` escrito à mão continua comentado | feature |
| T2 | Saída apagada ao trocar | Teste manual: célula executada → trocar linguagem → área de saída vazia | feature |
| T2 | Realce SQL | `grep -n '@codemirror/lang-sql' frontend/package.json frontend/src/components/notebook/CodeEditor.tsx` → presente nos dois | feature |
| T2 | Estilo do seletor restrito ao gatilho (code review r1, minor) | `grep -n 'languageMenu button' frontend/src/components/notebook/Notebook.module.css` → sem match; a regra de estilo do seletor mira só o botão gatilho (`aria-haspopup` ou classe própria) | bugfix |
| T2 | Sem troca de linguagem com a célula em execução ou na fila (code review r1, minor) | `frontend/src/components/notebook/CellHeader.tsx`: o seletor fica desabilitado quando a célula está `running`/`queued` (grep do `disabled` ligado a esse estado); teste manual: célula rodando → seletor não abre | bugfix |

## Arquivos previstos
- `backend/src/notisbook/kernels/protocol.py` — T1
- `backend/src/notisbook/kernels/service.py` — T1
- `backend/src/notisbook/api/sessions.py` — T1
- `backend/src/notisbook/kernels/sql_cell.py` — T1
- `frontend/src/components/notebook/CellHeader.tsx` — T2
- `frontend/src/components/notebook/Cell.tsx` — T2
- `frontend/src/components/notebook/CodeEditor.tsx` — T2
- `frontend/src/components/notebook/Notebook.module.css` — T2
- `frontend/src/state/notebook.ts` — T2
- `frontend/src/state/kernel.ts` — T2
- `frontend/src/ws/protocol.ts` — T2
- `frontend/src/ws/session.ts` — T2 (registrado na r1: o frame é montado aqui; não estava previsto)
- `frontend/package.json` — T2
- `frontend/package-lock.json` — T2

## Fora de escopo
- Grade tipada no estilo Databricks (mimetype `vnd.notisbook.table+json`, colunas com tipo, truncamento estruturado) — passo futuro, sem quebrar este contrato.
- Várias instruções por célula e magic `%sql` — decisões D5/D6.
- Cancelar o job na JVM ao interromper a célula — risco já conhecido, fora desta demanda.
- Teto de tamanho para `display_data`/`execute_result` — risco pré-existente.
- **Documentação de produto** — nenhuma.

## Não mexer
- `backend/src/notisbook/kernels/introspect.py` (canal de probe do Catalog)
- `backend/src/notisbook/spark/kernelspec.py` e os ambientes Spark já instalados
- Notebooks existentes sem `metadata.notisbook` continuam abrindo e executando como Python

## Status
- [x] T1 (a584669)  - [x] T2 (bddbe22 + 2da4426 — code review r2 aprovou)

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 115816 | 82157 |
| 0 | software-architect | OK | 222461 | 57670 |
| 1 | python-engineer | OK | 50973 | 42214 |
| 2 | python-engineer | OK | 90711 | 58803 |
| 2 | general-purpose (code-review) | OK | 122207 | 81241 |
| 2 | plan-auditor | OK | 47038 | 27560 |
| 2 | python-engineer (code review r1) | OK | 34694 | 39436 |
| 2 | general-purpose (code-review r2) | OK | 57538 | 73653 |
| 2 | plan-auditor (r2) | OK | 43900 | 27349 |
| — | memory-manager | OK | 19596 | 46620 |
<!-- effort-ledger:end -->
