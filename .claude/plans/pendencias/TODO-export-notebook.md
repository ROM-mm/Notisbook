# Pendências cosméticas do export do notebook

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-09 10:28:02 -0300
Modificação: 2026-11-09 11:00:24 -0300
Finalização: —

## Objetivo

Nits do code review do plano `export-notebook` (rodada 1), fora do gatilho do loop; retomar só se o operador decidir.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `backend/src/notisbook/export/html_report.py:33` — `url_relative: deny` remove `href` de links só-âncora (`#secao`); permitir `#…` via `attribute_filter` | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/export/html_report.py:210` — contagem de células do cabeçalho inclui células vazias omitidas; usar `len(sections)` | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/export/common.py:6,8` — reexport de `validate_notebook`; importar direto de `notebooks.store` em `api/export.py` | python-engineer | — | 1 | escrita |
| T4 | `frontend/src/api/http.ts:140-157` — `requestBlob` duplica montagem de body/fetch de `request`; extrair `send()` | python-engineer | — | 1 | escrita |
| T5 | `frontend/src/lib/download.ts:11` — `revokeObjectURL` com 0 ms; usar 1000–5000 ms | python-engineer | — | 1 | escrita |
| T6 | `backend/src/notisbook/export/py_source.py:27-31` — teste de magic/`!` linha a linha reescreve linhas dentro de string tripla; pular strings via `tokenize` ou documentar | python-engineer | — | 1 | escrita |
| T7 | `backend/src/notisbook/api/export.py:91` — header CSP `sandbox; default-src 'none'` bloqueia estilo inline e `data:` se o HTML abrir direto da resposta; alinhar com a meta CSP | python-engineer | — | 1 | escrita |
| T8 | `backend/src/notisbook/export/py_source.py:14` — falta espaço após `=` em `_BLOCK_COMMENT =re.compile`; rodar ruff format | python-engineer | — | 1 | escrita |
| T9 | `backend/src/notisbook/export/html_report.py:21` — `_LOGO_SVG` é cópia de `frontend/public/favicon-light.svg`; comentário apontando a origem | python-engineer | — | 1 | escrita |
| T11 | `backend/src/notisbook/export/html_report.py:206,211` — rótulo "horário de Brasília" repetido; constante `_TZ_LABEL` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4, T5, T6, T7, T8, T9, T11

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Link `[x](#a)` mantém `href="#a"` no relatório | gerar HTML com esse markdown; `grep -c 'href="#a"'` ≥ 1 | refactor |
| T2 | Contagem do cabeçalho = seções exibidas | notebook com 1 célula vazia: número no cabeçalho = nº de `<section` | refactor |
| T3 | `common.py` sem reexport de `validate_notebook` | `grep -n validate_notebook backend/src/notisbook/export/common.py` → 0 | refactor |
| T4 | Um único `fetch` em `http.ts` | `grep -c 'fetch(' frontend/src/api/http.ts` → 1; typecheck exit 0 | refactor |
| T5 | Revogação adiada ≥ 1000 ms | `grep -nE 'setTimeout\(.*[1-9][0-9]{3}' frontend/src/lib/download.ts` → ≥ 1 | refactor |
| T6 | Linha `%d` dentro de `"""..."""` preservada | célula com `s = """\n%d\n"""`: o `.py` contém a linha `%d` intacta | refactor |
| T7 | Header CSP inclui `img-src data:` e `style-src 'unsafe-inline'` | `curl -i POST /api/export/html` → header contém ambos | refactor |
| T8 | `py_source.py` formatado | `uv run ruff format --check backend/src/notisbook/export/py_source.py` → exit 0 | refactor |
| T9 | Origem do ícone documentada | `grep -n "favicon-light.svg" backend/src/notisbook/export/html_report.py` → ≥ 1 | refactor |
| T11 | Rótulo do fuso definido uma vez | `grep -c "horário de Brasília" backend/src/notisbook/export/html_report.py` → 1 | refactor |

## Arquivos previstos
- `backend/src/notisbook/export/html_report.py` — T1, T2, T9, T11, T11
- `backend/src/notisbook/export/common.py` — T3
- `backend/src/notisbook/api/export.py` — T3, T7
- `backend/src/notisbook/export/py_source.py` — T6, T8
- `frontend/src/api/http.ts` — T4
- `frontend/src/lib/download.ts` — T5

## Fora de escopo
- Qualquer mudança de comportamento do export além dos itens acima.
- **Documentação de produto** — nenhuma.

## Não mexer
- Contrato da rota `/api/export` e formatos gerados.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6  - [ ] T7  - [ ] T8  - [ ] T9  - [ ] T11

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T5 resolvido (revokeObjectURL adiado 10 s)
- T6 resolvido (magic/! dentro de string tripla preservado)
