# Export do notebook (.py, .ipynb para Databricks, .html)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-09 10:18:13 -0300
Modificação: 2026-11-09 11:03:53 -0300
Finalização: 2026-11-09 11:03:53 -0300

## Objetivo

O menu File passa a exportar o notebook aberto, tal como está na tela (alterações não salvas incluídas), em três formatos: `.py` no formato Databricks notebook source (Spark SQL vira `spark.sql("""...""")`, DuckDB vira bloco comentado com aviso), `.ipynb` para importar no Databricks e `.html` como relatório legível e autocontido. O `.dbc` foi trocado por `.ipynb` porque a estrutura interna dele não é documentada publicamente, e o Databricks importa `JUPYTER` oficialmente, com as saídas. O backend só transforma o conteúdo recebido: não lê nem grava disco, e a regra do store que só aceita `.ipynb` fica intacta.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Backend: pacote `export/` com `common` (linguagem da célula, nome de arquivo saneado, validação via nbformat) e `py_source` (Databricks source) | python-engineer | — | 1 | escrita |
| T2 | Backend: `html_report` (relatório autocontido, sem JS, CSP, nh3 + markdown-it-py `js-default`, CSS próprio com `--color-border-strong`/`.nb-grid*`/`.dataframe`, imagens data URI ≤ 10 MB, stderr/erro sem ANSI) + `uv add nh3 markdown-it-py` | python-engineer | T1 | 2 | escrita |
| T3 | Backend: router `POST /api/export/{py\|ipynb\|html}` com `require_token`, limite de 50 MB (413), notebook inválido 422, `Content-Disposition` RFC 6266, `nosniff`, `no-store`; registro em `app.py` | python-engineer | T2 | 3 | escrita |
| T4 | Frontend: `requestBlob` em `http.ts`, `api/export.ts`, `lib/download.ts`, itens rotulados só pelo formato — "Export .ipynb", "Export .py", "Export .html", sem nome de ferramenta/plataforma — no File após separador, desabilitados sem notebook pronto | python-engineer | T3 | 4 | escrita |
| T5 | Ampliação pedida pelo operador: rodapé do HTML "Exportado pelo <ícone> Notisbook em <data/hora de São Paulo>"; ícone = `frontend/public/favicon-light.svg` embutido como data URI; timestamp do cabeçalho também em America/Sao_Paulo | python-engineer | T4 | 5 | escrita |
| T6 | Pedido do operador (ex-pendência T10): "Exportado em" do cabeçalho do HTML com "(horário de Brasília)" | python-engineer | T5 | 6 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3
- Wave 4 (serial, escrita): T4
- Wave 5 (serial, escrita): T5
- Wave 6 (serial, escrita): T6

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Exportar o estado em memória via `POST`, sem tocar disco | arquivo igual à tela, sem salvar como efeito colateral; elimina path traversal | parecer do software-architect; `store.py:124-127` | GET lendo do disco (exporta desatualizado); export só no frontend (duplica lógica) |
| D2 | Prefixo próprio `/api/export` | `POST /api/contents/{path:path}` captura qualquer subcaminho | `api/contents.py:71` | rota sob `/api/contents` |
| D3 | `.py` no formato Databricks notebook source; `spark.sql("""...""")` solto, sem `display` | importa em células no Databricks e continua Python válido | Context7 docs Databricks; decisão do operador (3) | `# MAGIC %sql`; `display(spark.sql(...))` |
| D4 | Célula DuckDB vira bloco comentado com aviso | motor diferente; converter para Spark seria semanticamente errado | `kernels/sql_cell.py:143-170`; decisão do operador | `spark.sql`; `duckdb.sql` |
| D5 | `.dbc` substituído por `.ipynb` para Databricks | estrutura do `.dbc` não documentada (`unverified`); import `JUPYTER` é oficial | Context7 Databricks API (formatos SOURCE/JUPYTER/DBC); decisão do operador (1=a) | `.dbc` por engenharia reversa; só `.py` |
| D6 | Sanitização com `nh3` + `markdown-it-py` (`js-default`), CSP sem script | bibliotecas mantidas; `bleach` descontinuado; HTML aberto fora do app | Context7 nh3 e markdown-it-py v4.2.0 | bleach; sem sanitização |
| D8 | Rótulos do menu só com o formato de saída | preferência do operador | sem evidência — decisão do operador | "Export for Databricks (.ipynb)", "Export as HTML report" |
| D9 | Ícone do rodapé embutido como `<img src="data:image/svg+xml;base64,...">` do favicon claro | CSP do relatório só permite `img-src data:`; arquivo continua autocontido | `frontend/public/favicon-light.svg`; CSP em html_report.py | SVG inline (nh3/CSP), PNG externo |
| D10 | Horário do relatório em America/Sao_Paulo via `zoneinfo`, formato `dd/mm/aaaa HH:MM:SS (horário de Brasília)` | pedido do operador; independe do fuso do servidor | sem evidência — decisão do operador | fuso local do servidor |
| D7 | Limites: 50 MB por notebook, 10 MB por imagem (acima vira aviso) | DoS em payload/arquivo gerado | sem evidência — decisão do operador (2=ok) | sem limite |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `.py` abre com o cabeçalho Databricks e separa células | gerar `.py` de um notebook com markdown, Python, Spark SQL e DuckDB: 1ª linha `# Databricks notebook source`; `grep -c '^# COMMAND ----------$'` = nº de células não vazias − 1 | feature |
| T1 | `.py` é Python válido e o SQL com `"""` e `\` volta idêntico | `python -I -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" <arquivo.py>` → exit 0; `ast.literal_eval` da string do `spark.sql` = source original da célula | feature |
| T1 | DuckDB comentado com aviso, sem `spark.sql` | célula DuckDB aparece só com linhas iniciadas por `# ` e a linha de aviso `NOTISBOOK:` | feature |
| T1 | Célula Spark SQL com várias instruções gera um `spark.sql` por instrução (`;` dentro de string/comentário não separa); sem `display` (D3) | notebook com `CREATE TABLE t AS SELECT 1; SELECT ';' AS x -- a;b`: `ast.parse` ok, 2 chamadas `spark.sql`, `literal_eval` de cada = instrução original | bugfix |
| T1 | Linhas de magic `%%` (ex.: `%%time`) não quebram o `.py` | célula Python iniciada por `%%time`: `ast.parse` ok e a linha sai como `# MAGIC %%time` ou comentário | bugfix |
| T1 | Magic de célula `%%` prefixa a célula INTEIRA com `# MAGIC` | célula `%%sql\nSELECT 1\nFROM t`: `ast.parse` ok e as 3 linhas saem como `# MAGIC ...`; célula com `%pip install x` + código Python mantém o código como Python | bugfix |
| T2 | HTML sem execução de script | `grep -Eic '<script|javascript:| on[a-z]+=' relatorio.html` → 0 numa exportação cujo notebook contém `<script>` e `onerror=` em saída `text/html` | feature |
| T2 | HTML autocontido com CSP, índice e imagens | `grep -c 'Content-Security-Policy'` ≥ 1; `grep -c 'data:image/png;base64'` ≥ 1 com saída de imagem; teste manual: tabela Spark SQL com bordas, stderr destacado, sem códigos ANSI | feature |
| T2 | Dependências adicionadas pelo lock | `grep -nE '^name = "(nh3\|markdown-it-py)"' backend/uv.lock` → 2 ocorrências | constraint |
| T3 | Rota devolve anexo com cabeçalhos corretos | `curl -i -X POST /api/export/py` autenticado → 200, `Content-Disposition: attachment; filename=...; filename*=UTF-8''...`, `X-Content-Type-Options: nosniff` | feature |
| T3 | Erros do contrato | sem token → 401; formato `dbc` → 422; corpo > 50 MB → 413; notebook inválido → 422 | feature |
| T4 | Itens do menu sem nome de ferramenta/plataforma | `grep -nE "Export (as|for)|Databricks|Python \(|HTML report" frontend/src/components/shell/Topbar.tsx` → 0 ocorrências; `grep -cE "Export \.(ipynb|py|html)" frontend/src/components/shell/Topbar.tsx` → 3 | feature |
| T4 | Menu exporta e baixa os três formatos | teste manual: File → cada item baixa o arquivo com o nome do notebook e inclui uma célula editada e não salva | feature |
| T4 | Typecheck limpo | `npm --prefix frontend run typecheck` → exit 0 | constraint |
| T5 | Rodapé com ícone, "Notisbook" e hora de São Paulo | HTML gerado contém `<footer`, `Exportado pelo`, `Notisbook` e `data:image/svg+xml;base64` dentro do footer; com `generated_at` = 2026-11-09T13:00:00Z o footer mostra `09/11/2026 10:00:00` | feature |
| T5 | Cabeçalho e rodapé com o mesmo horário de São Paulo | mesmo HTML: string `09/11/2026 10:00:00` presente no header e no footer; sem `isoformat` em UTC | feature |
| T6 | Cabeçalho com fuso explícito | `to_html_report` com generated_at=2026-11-09T13:00Z: HTML contém `Exportado em 09/11/2026 10:00:00 (horário de Brasília)` e o rodapé segue igual | feature |

## Arquivos previstos
- `backend/src/notisbook/export/__init__.py` — T1
- `backend/src/notisbook/export/common.py` — T1
- `backend/src/notisbook/export/py_source.py` — T1
- `backend/src/notisbook/notebooks/store.py` — T1
- `backend/src/notisbook/export/html_report.py` — T2, T5, T6
- `backend/pyproject.toml` — T2
- `backend/uv.lock` — T2
- `backend/src/notisbook/api/export.py` — T3
- `backend/src/notisbook/app.py` — T3
- `frontend/src/api/http.ts` — T4
- `frontend/src/api/export.ts` — T4
- `frontend/src/lib/download.ts` — T4
- `frontend/src/components/shell/Topbar.tsx` — T4
- `frontend/src/state/notebook.ts` — T4

## Fora de escopo
- `.dbc` — formato não documentado (D5).
- Destaque de sintaxe no HTML — dependência extra sem requisito.
- Testes automatizados — não pedidos; critérios são especificação.
- **Documentação de produto** — README/ARCHITECTURE não descrevem o export. Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- Regra `_require_notebook_name` de `store.py` (só `.ipynb`) e o fluxo de Save.
- `kernels/sql_cell.py` e o HTML das saídas gerado pelo kernel.
- Rotas existentes de `/api/contents`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 87098 | 54341 |
| 0 | software-architect | OK | 169486 | 62054 |
| 1 | python-engineer | OK | 198139 | 79950 |
| 1 | code-review | OK | 107341 | 76257 |
| 1 | plan-auditor | OK | 30955 | 24597 |
| 2 | python-engineer | OK | 36919 | 33672 |
| 2 | code-review | OK | 69999 | 71563 |
| 3 | python-engineer | OK | 23158 | 30251 |
| 3 | code-review | OK | 53915 | 71321 |
| 3 | plan-auditor | OK | 33610 | 25829 |
| 5 | python-engineer | OK | 33320 | 37822 |
| 5 | code-review | OK | 49384 | 72279 |
| 5 | plan-auditor | OK | 44187 | 29245 |
| 6 | python-engineer | OK | 25955 | 29324 |
| 6 | code-review | OK | 58367 | 72766 |
| 6 | plan-auditor | OK | 29595 | 25705 |
| 7 | memory-manager | OK | 21217 | 43022 |
<!-- effort-ledger:end -->
