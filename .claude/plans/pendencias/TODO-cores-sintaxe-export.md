# Pendências cosméticas — cores de sintaxe no export HTML

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

## Objetivo

Nits do code review do plano `cores-sintaxe-export`, fora do gatilho de correção.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `backend/src/notisbook/export/html_report.py:227` — `sql = language != "python"` manda qualquer linguagem nova ao SqlLexer; usar `language in ("sql", "duckdb")` | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/export/html_report.py:255` — `cell_language(cell)` chamado duas vezes; guardar em variável local | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/export/html_report.py:23` — import de `_TokenType` (privado do Pygments) só para anotação; trocar por alias local | python-engineer | — | 1 | escrita |
| T4 | `backend/src/notisbook/export/html_report.py:209,241` — exceção "SQL Name.Builtin é tipo" duplicada em `_token_class` e na condição de chamada; escolher `callable_names` conforme o lexer | python-engineer | — | 1 | escrita |
| T5 | `backend/src/notisbook/export/html_report.py:67` — comentário diz que Name.Builtin fica sem cor; corrigir (tipo em SQL, função quando chamado) | python-engineer | — | 1 | escrita |
| T6 | `backend/src/notisbook/export/html_report.py:219` — docstring de `_call_flags` em pt-BR destoa das vizinhas em inglês; padronizar idioma | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4, T5, T6

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Seleção de lexer explícita | `grep -n 'in ("sql", "duckdb")' backend/src/notisbook/export/html_report.py` | refactor |
| T2 | Linguagem calculada uma vez por célula | leitura da montagem da célula de código em `html_report.py` | refactor |
| T3 | Sem import de símbolo privado do Pygments | `grep -n "_TokenType" backend/src/notisbook/export/html_report.py` sem import de `pygments.token` | refactor |
| T4 | Regra SQL Name.Builtin em um só lugar | leitura de `_highlight_code`/`_token_class` em `html_report.py` | refactor |
| T5 | Comentário do mapa de tokens fiel ao comportamento | leitura de `html_report.py` junto a `_TOKEN_CLASSES` | refactor |
| T6 | Docstrings do módulo num idioma só | leitura das docstrings de `html_report.py` | refactor |

## Arquivos previstos
- `backend/src/notisbook/export/html_report.py` — T1, T2, T3, T4, T5, T6

## Fora de escopo
- Mudança de cores ou de comportamento do realce.
- **Documentação de produto** — nenhuma.

## Não mexer
- `_ALLOWED_CLASSES` e `_SANITIZE` de `html_report.py`

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
