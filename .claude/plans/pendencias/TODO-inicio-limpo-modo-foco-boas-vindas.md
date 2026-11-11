# Pendências cosméticas — início limpo, modo foco e boas-vindas

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-10
Modificação: 2026-11-10
Finalização: —

## Objetivo

Resolver os nits do code review do início limpo / modo foco, sem mudar comportamento.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| N1 | `frontend/src/components/shell/AppShell.tsx:39` — `navigator.platform` deprecado; seguir o padrão `e.metaKey \|\| e.ctrlKey` de `NotebookView.tsx:112` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N1

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| N1 | sem detecção de plataforma deprecada | `grep -n "navigator.platform" frontend/src/components/shell/AppShell.tsx` → sem saída | fix |

## Arquivos previstos
- `frontend/src/components/shell/AppShell.tsx`

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/api/**`, `frontend/src/ws/**`, `backend/**`.

## Status
- [ ] N1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
