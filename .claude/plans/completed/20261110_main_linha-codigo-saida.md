# Linha divisória entre código e saída da célula

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-10 12:48:22 -0300
Modificação: 2026-11-10 13:40:51 -0300
Finalização: 2026-11-10 13:40:51 -0300

## Objetivo

Separar visualmente o código da saída na célula com uma linha de 1px (`--color-border-strong`) de borda a borda do cartão, como no mockup v2 aprovado. A saída hoje é irmã solta do campo de código dentro de `.cellBody`, então a linha vai num contêiner `.outputBox` que só existe quando há saída — CSS puro dependeria de seletor frágil. O estilo interno das saídas não muda.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Envolver a saída em `.outputBox` (só quando existir) e desenhar a linha superior de borda a borda | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `.outputBox` com linha superior de 1px | `grep -A8 "^\.outputBox" frontend/src/components/notebook/Notebook.module.css \| grep "border-top: 1px solid var(--color-border-strong)"` encontra | feature |
| T1 | Cell.tsx só ganha o wrapper condicional | `git diff <baseline> -- frontend/src/components/notebook/Cell.tsx \| grep -E "^[+-].*(onClick\|onDoubleClick\|onRun\|onChange\|title=)"` sem saída; `git diff <baseline> -- frontend/src/components/notebook/Cell.tsx \| grep -c "outputBox"` ≥ 1 | constraint |
| T1 | Saídas intocadas | `git diff <baseline> -- frontend/src/components/outputs` vazio | constraint |
| T1 | Build do frontend passa | `npm --prefix frontend run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/src/components/notebook/Cell.tsx` — T1
- `frontend/src/components/notebook/Notebook.module.css` — T1

## Fora de escopo
- Estilo interno das saídas e o export HTML.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/components/outputs/**`, `backend/**`, `frontend/src/styles/global.css`.
- Handlers, textos e a ordem dos elementos em `Cell.tsx`.

## Status
- [x] T1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 31562 | 33014 |
<!-- effort-ledger:end -->
