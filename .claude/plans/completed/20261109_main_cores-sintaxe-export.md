# Cores de sintaxe no código do export HTML

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-09 16:31:04 -0300
Modificação: 2026-11-09 17:09:46 -0300
Finalização: 2026-11-09 17:09:46 -0300

## Objetivo

O código das células no export HTML ganha as mesmas cores de sintaxe do editor do notebook (Python e SQL, tema claro e escuro). Hoje sai só escapado num `pre` cinza (`html_report.py:183`). O export proíbe JS (CSP), então a tokenização é no backend com Pygments, reaproveitando a paleta `--syntax-*` do app (`frontend/src/components/notebook/Notebook.module.css:8-56`); app e export não compartilham CSS, por isso a paleta é copiada.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Pygments como dependência do backend; código da célula tokenizado em spans com classes curtas espelhando `--syntax-*` (pós-passo: nome seguido de `(` = função), texto escapado; paleta clara e escura no `_CSS`; comentário cruzado em `Notebook.module.css` e `_CSS` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Tokenizar no backend com Pygments | export sem JS; Python puro; um lexer SQL serve Spark e DuckDB como no app | `html_report.py:17,183`; `Cell.tsx:42-46`; pygments ausente de `backend/uv.lock` | tokens vindos do frontend via `@lezer/highlight` (cor exata, mas muda `ExportBody` e export via API sairia sem cor); lexer próprio |
| D2 | Código segue fora do nh3: spans gerados pelo backend sobre texto já escapado | allowlist do nh3 não muda | `html_report.py:91,118,183` | passar o código pelo nh3 com classes de token liberadas |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Pygments declarado e travado | `grep -n pygments backend/pyproject.toml backend/uv.lock` com resultado nos dois | feature |
| T1 | Código Python e SQL sai com spans de token | export de exemplo gerado com `to_html_report` contém `<span class=` dentro de `<pre><code>` para célula Python e SQL | feature |
| T1 | Paleta do app nos dois temas | os hex de `--syntax-*` de `Notebook.module.css:8-40` aparecem no `_CSS` de `html_report.py` (claro e `@media (prefers-color-scheme: dark)`) | feature |
| T1 | `display(df)`: `display` com a cor de função | export de exemplo marca `display` com a classe de função | feature |
| T1 | Código continua escapado | export de célula com `print("<script>x</script>")` contém `&lt;script&gt;` e nenhuma tag `<script>` no corpo | constraint |
| T1 | Allowlist e sanitização do nh3 inalteradas | `git diff <baseline> -- backend/src/notisbook/export/html_report.py` não altera `_ALLOWED_CLASSES` nem `_SANITIZE` | constraint |
| T1 | Visual igual ao do notebook | teste manual: abrir export no navegador (claro/escuro do sistema) e comparar com o editor | feature |
| T1 | Realce linear no número de tokens (sem slice da lista por token) | leitura de `html_report.py:_call_flags` (passada única por índice; `grep -n "tokens\[index + 1 :\]"` sem resultado) + célula Python de 20.000 linhas com chamadas realçada em poucos segundos (medido) | bugfix |
| T1 | Tipos SQL parametrizados com cor de tipo | export de `CAST(x AS VARCHAR(10))` e `DECIMAL(10,2)` marca `VARCHAR`/`DECIMAL` com a classe de tipo, não `t-fn` | bugfix |
| T1 | Fusão de tokens vizinhos linear (sem concatenar string a cada token) | leitura de `_highlight_code` (lista por grupo + um `join`; `grep -n "parts\[-1\] = "` sem resultado) + tempo de `_highlight_code` para `"x y z\n" * n` com 1,2 MB ≤ 2,5× o tempo com 600 KB (crescimento ~linear, lex incluso) | bugfix |
| T1 | Paleta completa do app no `_CSS` (achado da auditoria) | os 12 hex de `--syntax-*` do tema claro (`Notebook.module.css:10-21`) e os 12 do escuro (`:31-42`) aparecem no `_CSS` de `html_report.py`, incluindo property/heading/link | bugfix |

## Arquivos previstos
- `backend/pyproject.toml` — T1
- `backend/uv.lock` — T1
- `backend/src/notisbook/export/html_report.py` — T1
- `frontend/src/components/notebook/Notebook.module.css` — T1

## Fora de escopo
- Tema escuro forçado (`data-theme`) no arquivo exportado — o export só segue `prefers-color-scheme`.
- Dialetos SQL separados para Spark/DuckDB — o app também usa um SQL genérico.
- Testes automatizados — não pedidos.
- **Documentação de produto** — nenhuma.

## Não mexer
- Valores das cores `--syntax-*` do app (só comentário em `Notebook.module.css`)
- `_ALLOWED_CLASSES` e `_SANITIZE` de `html_report.py`
- `backend/src/notisbook/kernels/sql_cell.py`
- `frontend/src/components/outputs/HtmlOutput.tsx`

## Status
- [x] T1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 85586 | 39641 |
| 1 | python-engineer | OK | 59186 | 48148 |
| 1 | code-review (skill) | ajustes necessários | 250077 | 69187 |
| 1 | python-engineer | OK | 18003 | 30224 |
| 1 | code-review (skill) | ajustes necessários | 95922 | 61429 |
| 1 | python-engineer | OK | 29363 | 29243 |
| - | knowledge-engineer | OK | 36339 | 27164 |
| 1 | code-review (skill) | aprovar | 47418 | 60111 |
| 1 | plan-auditor | DIVERGENTE | 58446 | 30438 |
| 1 | python-engineer | OK | 12650 | 26178 |
| 1 | code-review (skill) | aprovar | 41429 | 59432 |
| 1 | plan-auditor | PARCIALMENTE AUDITÁVEL | 33514 | 27012 |
| - | memory-manager | OK | 20229 | 46801 |
<!-- effort-ledger:end -->
