# Tabela do DataFrame no visual Neo-Brutalism pastel

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-10 23:04:48 -0300
Modificação: 2026-11-10 23:09:24 -0300
Finalização: 2026-11-10 23:09:24 -0300

## Objetivo

A tabela de resultado do DataFrame (CSS embutido no Shadow DOM de `frontend/src/components/outputs/HtmlOutput.tsx`) passa a seguir o Neo-Brutalism pastel do redesign (plano `completed/20261110_main_redesign-neo-brutalism-pastel.md`): cabeçalho azul pastel, bordas sólidas `--ink`, zebra suave, cantos retos, claro e escuro. Somente visual — dados, paginação, cabeçalho sticky e comportamento iguais. Referência: `.claude/plans/mockups/neo-brutalism-pastel/sections/P09.png` e `styles.css`.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Restilizar o CSS embutido de HtmlOutput.tsx com os tokens de `tokens.css` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Build sem erro | `cd frontend && npm run build` → exit 0 | constraint |
| T1 | Typecheck limpo | `cd frontend && npm run typecheck` → exit 0 | constraint |
| T1 | Tabela usa os tokens novos | `grep -nE "var\(--(ink\|blue)" frontend/src/components/outputs/HtmlOutput.tsx` → presentes | feature |
| T1 | Sem canto arredondado | `grep -nE "border-radius:\s*[^0;]" frontend/src/components/outputs/HtmlOutput.tsx` → sem saída | feature |
| T1 | (review r1) Cabeçalho sticky sem borda de 1px do kernel SQL | regra de `thead th` dentro de `.nb-grid` em `HtmlOutput.tsx` com especificidade maior que (0,1,2) e `border-bottom: 0` | fix |
| T1 | Nada fora do visual mudou | `git diff --stat <baseline> -- frontend/src/api frontend/src/state frontend/src/ws frontend/src/lib backend` → vazio | constraint |

## Arquivos previstos
- `frontend/src/components/outputs/HtmlOutput.tsx` — T1

## Fora de escopo
- Nits N1–N10 de `.claude/plans/pendencias/TODO-redesign-neo-brutalism-pastel.md`.
- Export HTML do backend (D4 = b do plano do redesign).
- **Documentação de produto** — nenhuma.

## Não mexer
- Lógica do componente, markup HTML vindo do kernel, textos.
- `frontend/src/api/**`, `frontend/src/state/**`, `frontend/src/ws/**`, `frontend/src/lib/**`, `backend/**`.

## Status
- [x] T1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer (T1) | OK | 36739 | 36728 |
| 1 | python-engineer (T1 review r1) | OK | 17652 | 28992 |
<!-- effort-ledger:end -->
