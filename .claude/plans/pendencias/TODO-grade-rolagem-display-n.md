# Pendências cosméticas — grade com rolagem e display(df, n)

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

## Objetivo

Nits do code review do plano `grade-rolagem-display-n`, fora do gatilho de correção.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/components/outputs/HtmlOutput.tsx:27` — thead sticky tem box-shadow + border-bottom (linha dupla 2px); zerar a borda no cabeçalho sticky (o `<style>` do kernel em `sql_cell.py:63` também a define) | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/kernels/sql_cell.py:202` — `message` montada antes da validação; montar só nos ramos de erro | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/kernels/sql_cell.py:85` — dica `use display(df, n=...)` aparece mesmo com n=1000 truncado; anexar só quando limit < MAX_ROWS | python-engineer | — | 1 | escrita |
| T4 | `backend/src/notisbook/kernels/sql_cell.py:220` — wrapper sem `__doc__`/`__name__`/`__qualname__` do original (sem functools.wraps) | python-engineer | — | 1 | escrita |
| T5 | `backend/src/notisbook/kernels/sql_cell.py:79` — chamar `limit_var()` em `install_display()` para a ContextVar existir no STATE desde a instalação | python-engineer | — | 1 | escrita |
| T6 | `backend/src/notisbook/kernels/sql_cell.py:78` — comentários novos misturam inglês/pt-BR (:78,:84,:221,:244,:252); padronizar em pt-BR | python-engineer | — | 1 | escrita |
| T7 | (obsoleto) `html_report.py:72` — números quebrando no meio: resolvido pela D9 (nowrap) do plano | — | — | 1 | escrita |
| T8 | `backend/src/notisbook/export/html_report.py:70-72` — seletor `.nb-grid th,.nb-grid td,.dataframe th,.dataframe td` repetido em duas regras (borda e nowrap); juntar numa só | python-engineer | — | 1 | escrita |
| T9 | `backend/src/notisbook/export/html_report.py:79` — `section.cell{break-inside:avoid-page}` empurra célula com grade alta para a página seguinte no print; liberar com `section.cell:has(.nb-grid){break-inside:auto}` | python-engineer | — | 1 | escrita |
| T10 | `backend/src/notisbook/export/html_report.py:71` — `.nb-grid{overflow-x:auto}` aninhado no `.out` que já rola; comentar o porquê (rolar só a grade) | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4, T5, T6, T7, T8, T9, T10

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Cabeçalho sticky com uma única linha inferior | `grep -n "border-bottom" frontend/src/components/outputs/HtmlOutput.tsx backend/src/notisbook/kernels/sql_cell.py` mostra a borda zerada/removida para `thead th` | refactor |
| T2 | Mensagem de erro de `n` construída só no caminho de erro | leitura de `sql_cell.py:check_n` — nenhuma atribuição de mensagem antes da validação | refactor |
| T3 | Dica só quando o limite é menor que MAX_ROWS | leitura de `sql_cell.py:footer_text` — condição `limit < MAX_ROWS` na dica | refactor |
| T4 | `display?` mostra a docstring do IPython | kernel: `display.__doc__` não vazio e `display.__name__ == "display"` | refactor |
| T5 | ContextVar criada na instalação | `grep -n "limit_var()" backend/src/notisbook/kernels/sql_cell.py` inclui `install_display` | refactor |
| T6 | Comentários do changeset em pt-BR | leitura das linhas citadas em `sql_cell.py` | refactor |
| T7 | (obsoleto — resolvido pela D9) | leitura | refactor |
| T8 | Sem regra duplicada para td/th da grade no export | leitura do `_CSS` de `html_report.py` — uma só regra `.nb-grid th,.nb-grid td,...` | refactor |
| T9 | Célula com grade não força salto de página | `grep -n "has(.nb-grid)" backend/src/notisbook/export/html_report.py` | refactor |
| T10 | Rolagem aninhada justificada | comentário pt-BR junto a `.nb-grid{overflow-x:auto}` em `html_report.py` | refactor |

## Arquivos previstos
- `frontend/src/components/outputs/HtmlOutput.tsx` — T1
- `backend/src/notisbook/kernels/sql_cell.py` — T1, T2, T3, T4, T5, T6
- `backend/src/notisbook/export/html_report.py` — T8, T9, T10

## Fora de escopo
- Qualquer mudança de comportamento da grade ou do display.
- **Documentação de produto** — nenhuma.

## Não mexer
- `_ALLOWED_CLASSES` e sanitização nh3 de `backend/src/notisbook/export/html_report.py`

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6  - [x] T7  - [ ] T8  - [ ] T9  - [ ] T10

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
