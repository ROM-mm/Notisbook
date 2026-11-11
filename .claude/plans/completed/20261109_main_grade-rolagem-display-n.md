# Grade com rolagem e display(df, n=50)

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-09 14:09:23 -0300
Modificação: 2026-11-09 15:53:36 -0300
Finalização: 2026-11-09 15:53:36 -0300

## Objetivo

(1) A grade HTML de DataFrame ganha altura máxima com rolagem nos dois eixos e thead sticky — hoje a barra horizontal já existe no host `.html` (`Outputs.module.css:66-70`), mas fica no fim de até 1000 linhas sem `max-height` e não aparece na tela; nenhuma coluna é omitida pelo kernel (`sql_cell.py:103-131`). (2) `display(df)` de DataFrame PySpark mostra 50 linhas por default e `display(df, n=<int>)` mostra `n`; `df` na última linha e células SQL/DuckDB seguem em 1000. Mecanismo de (2): wrapper marcado do `display` instalado pelo módulo oculto (`builtins.display`, `IPython.display.display`, `IPython.core.display_functions.display`) + `ContextVar` em `STATE` lida pelo formatter, porque o `ZMQDisplayPublisher` descarta kwargs desconhecidos em silêncio (IPython 9.18.1 / ipykernel 7.4.0, lido do fonte local — Context7 `unverified`).

(3) Ampliação de escopo pós-teste (operador, 2026-11-09): no export HTML a grade aparece inteira — hoje as linhas já saem todas, mas colunas largas passam dos 960px da página e ficam atrás de rolagem horizontal no fim da grade (`html_report.py:57,64`) e são cortadas na impressão (`:77`). O export não usa o CSS do app; só o `_CSS` de `html_report.py` define a grade ali.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `.nb-grid` com max-height (~640px), overflow auto nos dois eixos e `thead th` sticky com fundo por variável de tema, só no `SHADOW_CSS` | python-engineer | — | 1 | escrita |
| T2 | `display(..., n=)` keyword-only, default 50, teto 1000, wrapper idempotente + ContextVar; `_build(df, limit)`/`footer_text(..., limit)`; rodapé truncado com dica `— use display(df, n=...)`; `run`/`run_duckdb` usam o display original; docstring do módulo atualizado | python-engineer | — | 2 | escrita |
| T3 | No `_CSS` de `html_report.py`, células da grade em uma linha (`white-space:nowrap`, sem quebra, fonte normal), rolagem horizontal só em `.nb-grid`, sem max-height/overflow-y; `@media print` com fonte reduzida na grade e sem rolagem (reabertura D8: quebra de texto reprovada no teste) | python-engineer | — | 3 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3 (ampliação pós-teste)

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Rolagem resolvida no frontend (`SHADOW_CSS`), escopada a `.nb-grid` | corrige também outputs já salvos; não exige classe nova no export nh3 (descarta `style` inline) | `HtmlOutput.tsx:14-25`; `html_report.py:38-50` | wrapper no kernel (não corrige `.ipynb` salvos, exige allowlist no export) |
| D2 | Wrapper marcado do `display` em builtins + `IPython.display` + `display_functions`, limite via `ContextVar` em `STATE` | `n` some em silêncio em qualquer via não coberta; mantém um só formatter e uma só coleta (`limit+1`) | `interactiveshell.py:896`; `display_functions.py:290-353`; `sql_cell.py:190-204` | wrapper no `user_ns` (viola "nada no namespace", perde-se no `%reset`); só builtins (import explícito ignora `n`); proxy `_repr_mimebundle_`; inspeção de pilha |
| D3 | `n`: int via `operator.index`, sem `bool`, `1 ≤ n ≤ 1000`; inválido → erro antes de qualquer output (msg em inglês) | teto = `MAX_ROWS` protege o limite de 1 MB de saída por célula; clamp esconderia o erro | `sql_cell.py:26`; `TRUNCATION_NOTICE` em `service.py` | clamp silencioso |
| D4 | Rodapé segue dentro de `.nb-grid` e rola junto; truncado via display ganha `— use display(df, n=...)` | rodapé sempre visível exigiria mudar a estrutura HTML do kernel | `sql_cell.py:86-88` | rodapé fora do wrapper rolável |
| D6 | D4 revisada no loop de review: rodapé fica dentro de `.nb-grid` mas `position: sticky; bottom: 0; left: 0` com fundo de tema — sempre visível, sem mudar o HTML do kernel nem classe nova | achado minor do review: a dica `use display(df, n=...)` ficava escondida no fim da rolagem | parecer code review rodada 1 (`sql_cell.py:101-103`, `HtmlOutput.tsx:26`) | wrapper `nb-grid-wrap` no kernel (exige classe nova em `html_report.py`, que é Não mexer) |
| D7 | `register()` registra o formatter antes e instala o wrapper do display por último, em try/except próprio; `original_display()` não depende de `display_functions` | falha do wrapper era engolida pelo ensure e derrubava a grade inteira | parecer code review rodada 1 (`sql_cell.py:258`, `:177`, `:271`) | manter ordem atual |
| D5 | Efeito em libs de terceiros que chamam `display(spark_df)` (passam a 50) aceito; ADR não pedido | decisão do operador | `sem evidência` (decisão do operador) | ADR via skill `document` |
| D8 | Export HTML: grade cabe na largura da página por quebra de texto (tabela 100%, `overflow-wrap:anywhere`), cresce só na vertical, fonte menor na grade; impressão sem rolagem horizontal | pedido do operador: grade completa no export, esticando só na vertical | diagnóstico: `html_report.py:57,64,77`; `_ALLOWED_CLASSES` já permite `nb-grid` (`:38`) | rolagem só na grade (não mostra por completo); alargar a página (quebra o layout e corta na impressão); híbrida com largura mínima + rolagem |
| D9 | Sucede a D8: no export as células ficam em uma linha (nowrap, fonte normal), a grade rola na horizontal dentro de `.nb-grid` e cresce só na vertical; na impressão a grade usa fonte reduzida para caber mais colunas no papel | teste do operador reprovou a quebra de texto ("precisa de tudo em linha") | print do export enviado pelo operador em 2026-11-09 | manter quebra de texto (reprovada); alargar a página inteira |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Regra de rolagem e thead sticky existem só para a grade | `grep -n "nb-grid" frontend/src/components/outputs/HtmlOutput.tsx` encontra `max-height`, `overflow` e `position: sticky` no `SHADOW_CSS` | feature |
| T1 | Grade de 15 colunas × 2000 linhas mostra as duas barras dentro da tela e o cabeçalho fixo ao rolar, nos temas claro e escuro | teste manual no navegador: `div[data-output-mime="text/html"]` com `scrollWidth > clientWidth` e barra visível sem rolar a página até o fim | feature |
| T1 | Outputs de texto/stream e o host `.html` não mudam | `git diff <baseline> -- frontend/src/components/outputs/Outputs.module.css` vazio | constraint |
| T2 | Constante e limite parametrizado existem | `grep -nE "DISPLAY_ROWS = 50\|def _build\(df, limit" backend/src/notisbook/kernels/sql_cell.py` | feature |
| T2 | `display(spark.range(2000))` → 50 linhas, rodapé `showing the first 50 rows — use display(df, n=...)` | kernel 3.5.9 (clássico) e 4.3.0 (Connect) | feature |
| T2 | `display(df, n=7)` → 7 linhas; `display(spark.range(10), n=50)` → `10 rows` | kernel | feature |
| T2 | `df` na última linha, célula SQL e célula DuckDB seguem em 1000 linhas | kernel com `spark.range(2000)` / `select * from range(2000)`; `grep -n MAX_ROWS` em `run`/`_build_duckdb` | constraint |
| T2 | `n=0`, `n=True`, `n=2.5`, `n=1001` → célula falha sem output | kernel | feature |
| T2 | Funciona via `from IPython.display import display`, após `%reset -f`, após restart, e `h=display(df, display_id=True); h.update(df, n=5)` atualiza com 5 | kernel | feature |
| T2 | `display` fora do namespace e sem cadeia de wrappers | kernel: `'display' not in get_ipython().user_ns`; após 2 células SQL, `builtins.display._notisbook_original` não é wrapper | constraint |
| T1 | Rodapé `.nb-grid-footer` sticky no fundo e à esquerda dentro da grade | `grep -n "nb-grid-footer" frontend/src/components/outputs/HtmlOutput.tsx` mostra `position: sticky`, `bottom: 0`, `left: 0` e `background: var(` | bugfix |
| T2 | Formatter registrado antes do wrapper; falha do wrapper não impede a grade | leitura de `sql_cell.py:register` (formatter antes de `install_display`, este em try/except) + kernel com `install_display` forçado a lançar → `df` ainda renderiza grade | bugfix |
| T2 | `run`/`run_duckdb` não dependem de importar `IPython.core.display_functions` | `grep -n "display_functions" backend/src/notisbook/kernels/sql_cell.py` só dentro de `install_display`/try | bugfix |
| T3 | Células da grade do export em uma linha, com rolagem horizontal só na grade | `grep -n "nb-grid" backend/src/notisbook/export/html_report.py` mostra `white-space:nowrap` em td/th e `overflow-x:auto` em `.nb-grid`; sem `overflow-wrap:anywhere` | bugfix |
| T3 | Grade do export sem caixa de rolagem vertical | `grep -nE "nb-grid[^}]*(max-height\|overflow-y)" backend/src/notisbook/export/html_report.py` sem resultado | constraint |
| T3 | Impressão: grade sem rolagem e com fonte reduzida | bloco `@media print` em `html_report.py` com `overflow:visible` e `font-size` reduzido para a grade | feature |
| T3 | Export de notebook com grade 15 colunas × 60 linhas: cada valor numa linha, barra horizontal só na grade, todas as linhas visíveis | teste manual: exportar HTML pelo app e abrir no navegador (e imprimir em PDF) | bugfix |
| T3 | Allowlist do nh3 inalterada | `git diff 97fc1a3 -- backend/src/notisbook/export/html_report.py` não altera `_ALLOWED_CLASSES` | constraint |

## Arquivos previstos
- `frontend/src/components/outputs/HtmlOutput.tsx` — T1
- `backend/src/notisbook/kernels/sql_cell.py` — T2
- `backend/src/notisbook/export/html_report.py` — T3

## Fora de escopo
- Interação na grade (sort/filtro/paginação) — recusada na decisão vigente da grade.
- `df.show()` — continua texto.
- Limite de linhas para DataFrame pandas — `n` aceito e ignorado.
- Testes automatizados — não pedidos (policy de teste autoral).
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/components/outputs/Outputs.module.css`
- `_ALLOWED_CLASSES` e a sanitização nh3 de `backend/src/notisbook/export/html_report.py`
- `frontend/src/components/outputs/HtmlOutput.tsx` e `sql_cell.py` na wave 3
- Limites das células SQL/DuckDB (`MAX_ROWS = 1000`, `MAX_CELL_CHARS = 500`)

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 129505 | 53898 |
| 0 | software-architect | OK | 183353 | 49089 |
| 1 | python-engineer | OK | 17831 | 30762 |
| 2 | python-engineer | OK | 82707 | 47582 |
| 3 | code-review (skill) | ajustes necessários | 59151 | 62693 |
| 3 | python-engineer | OK | 75920 | 42919 |
| 3 | code-review (skill) | aprovar | 65548 | 67391 |
| 3 | plan-auditor | PARCIALMENTE AUDITÁVEL | 45988 | 31750 |
| - | knowledge-engineer | FAILED (rate limit) | — | — |
| - | knowledge-engineer | OK | 86566 | 37574 |
| 3 | python-engineer | OK | 56403 | 35404 |
| 3 | code-review (skill) | aprovar | 41884 | 60204 |
| 3 | plan-auditor | PARCIALMENTE AUDITÁVEL | 42107 | 30174 |
| 3 | python-engineer | OK | 44512 | 33769 |
| 3 | code-review (skill) | aprovar | 36939 | 56586 |
| 3 | plan-auditor | PARCIALMENTE AUDITÁVEL | 42170 | 32891 |
| - | memory-manager | OK | 18166 | 35876 |
<!-- effort-ledger:end -->
