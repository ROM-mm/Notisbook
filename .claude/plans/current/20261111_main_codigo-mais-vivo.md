# Código das células mais vivo — Fira Code + paleta estilo Databricks

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-11 01:52:23 -0300
Modificação: 2026-11-11 02:01:55 -0300
Finalização: —

## Objetivo

O código das células code (Python e SQL/DuckDB) parece apagado: o peso 500 pedido não está carregado (só JetBrains Mono 400/600 — `main.tsx:6-8`), a paleta é pastel/roxa, e operadores/nomes não se distinguem. Entrega: fonte Fira Code (com ligaduras) só no editor, palavras-chave em negrito, e paleta saturada no padrão Databricks das referências do operador — Python: keywords azul, nome em `def` e método chamado dourado, números verde, resto neutro; SQL: keywords azul, prefixos qualificadores (`main.data_science_adventure.`) dourado, nome final da tabela e colunas neutros, números verde. Fonte nova via variável `--font-code` exclusiva do editor para não alterar saídas e painéis, que usam `--font-mono`.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Adicionar `@fontsource/fira-code` e carregar pesos 500 e 700 | python-engineer | — | 1 | escrita |
| T2 | Variável `--font-code` (Fira Code, ligaduras ligadas) aplicada só ao editor, peso base 500 | python-engineer | T1 | 1 | escrita |
| T3 | Keywords em peso 700; comentário sem itálico | python-engineer | — | 1 | escrita |
| T4 | Paleta nova nos temas claro e escuro (inclusive bloco escuro duplicado) | python-engineer | — | 1 | escrita |
| T5 | SQL: prefixos qualificadores em dourado, nome final neutro | python-engineer | T4 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2 → T3 → T4 → T5

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Fonte via nova `--font-code`, não trocando `--font-mono` | `--font-mono` é usada em saídas, painéis de variáveis/dados/Spark/kernel | `grep -rn font-mono frontend/src` (≈20 usos) | trocar `--font-mono` global — descartado, muda o app inteiro |
| D2 | Negrito só nas keywords | escolha do operador; legibilidade | sem evidência — preferência do operador | negrito em todo o código |
| D3 | Ligaduras ligadas | escolha do operador | sem evidência — preferência do operador | desligar via `font-variant-ligatures: none` |
| D4 | Comentário sem itálico | Fira Code não tem itálico; evita oblíquo sintético | `@fontsource/fira-code` sem arquivos italic | manter itálico sintético |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Fira Code instalada e pesos 500/700 carregados | `grep -n '"@fontsource/fira-code"' frontend/package.json` retorna 1 linha; `grep -nE 'fira-code/(latin-)?500|fira-code/(latin-)?700' frontend/src/main.tsx` retorna 2 linhas | feature |
| T2 | Editor usa `--font-code` com Fira Code, peso 500 | `grep -n -- '--font-code:.*Fira Code' frontend/src/styles/tokens.css` ≥1; `grep -c 'var(--font-code)' frontend/src/components/notebook/editorTheme.ts` ≥3 | feature |
| T2 | `--font-mono` inalterada | `git diff <baseline> -- frontend/src/styles/tokens.css \| grep -c -- '^[-+].*--font-mono:'` = 0 | constraint |
| T3 | Keywords peso 700; comentário sem `fontStyle: "italic"` | `editorTheme.ts:HighlightStyle` — regra de `t.keyword` contém `fontWeight: "700"`; `grep -n 't.comment.*italic' frontend/src/components/notebook/editorTheme.ts` = 0 | feature |
| T4 | Paleta clara: keyword `#1f5fa8`, função/qualificador `#a8761a`, número `#13875a` | `grep -ciE '#1f5fa8\|#a8761a\|#13875a' frontend/src/styles/tokens.css` ≥3 | feature |
| T4 | Dois blocos escuros idênticos entre si | trecho `--sx-*` de `tokens.css` nos blocos `prefers-color-scheme: dark` e tema forçado: `diff` dos dois trechos vazio | constraint |
| T5 | SQL: qualificadores em dourado via regra só do SQL | `CodeEditor.tsx`/`editorTheme.ts`: símbolo da regra de qualificador registrado apenas no ramo `sql()` (`CodeEditor.tsx` ~linha 48) | feature |
| T5 | SQL: qualificador entre aspas (`QuotedIdentifier`, ex.: `"main"."schema".tbl`) também fica dourado (achado minor do review, rodada 1) | `grep -n 'QuotedIdentifier' frontend/src/components/notebook/editorTheme.ts` ≥1 no filtro de nós do `sqlQualifierHighlight` | feature |
| T5 | SQL: qualificador entre crases (`` `a`.`b`.c ``, citação nativa do Spark SQL) também fica dourado (achado minor do review, rodada 2) | `grep -n 'identifierQuotes' frontend/src/components/notebook/CodeEditor.tsx` ≥1 com crase no dialeto passado a `sql()` | feature |
| T1–T5 | Build passa | `cd frontend && npm run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/package.json` — T1
- `frontend/package-lock.json` — T1
- `frontend/src/main.tsx` — T1
- `frontend/src/styles/tokens.css` — T2, T4
- `frontend/src/components/notebook/editorTheme.ts` — T2, T3, T4
- `frontend/src/components/notebook/Notebook.module.css` — T4
- `frontend/src/components/notebook/CodeEditor.tsx` — T5
- `.claude/plans/pendencias/TODO-codigo-mais-vivo.md` — artefato de sessão (nits do review)

## Fora de escopo
- Export HTML (`backend/src/notisbook/export/html_report.py`) — operador adiou ("depois vemos").
- Dialeto DuckDB específico no `lang-sql` — não pedido; mantém `sql()` genérico.
- **Documentação de produto** — nenhuma.

## Não mexer
- `--font-mono` e as fontes de saídas/painéis (Outputs, Variables, Data, Spark, Kernel).
- Markdown renderizado (`Markdown.module.css`).
- Backend inteiro.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 77788 | 52382 |
| 1 | python-engineer | OK | 60821 | 44156 |
| 1 | code-review | ajustes necessários | 88218 | 70374 |
| 1 | plan-auditor | CONFORME | 32145 | 25685 |
| 2 | python-engineer | OK | 24674 | 28279 |
| 2 | plan-auditor | CONFORME | 25560 | 23525 |
| 2 | code-review | ajustes necessários | 56070 | 63494 |
| 3 | python-engineer | OK | 19639 | 27852 |
| 3 | plan-auditor | CONFORME | 26733 | 27737 |
| 3 | code-review | aprovar | 54044 | 65950 |
<!-- effort-ledger:end -->
