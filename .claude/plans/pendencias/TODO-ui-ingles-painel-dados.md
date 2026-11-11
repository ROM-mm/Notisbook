# Pendências cosméticas — comentários desatualizados pela tradução da UI

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 18:24:03 -0300
Modificação: 2026-11-06 18:26:07 -0300
Finalização: —

## Objetivo

Alinhar comentários que ficaram incorretos ou híbridos após a tradução da UI para inglês (nits do code review do plano ui-ingles-painel-dados).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/lib/paths.ts:39` — exemplos de `uniqueName` citam "Sem título.ipynb"; atualizar para "Untitled.ipynb" | python-engineer | — | 1 | escrita |
| T2 | `frontend/src/state/workspace.ts:132` — docstring cita "Sem título N.ipynb"; atualizar para "Untitled N.ipynb" | python-engineer | — | 1 | escrita |
| T3 | `frontend/src/components/files/format.ts:16` — exemplo "há 5 minutos" não bate com en-US | python-engineer | — | 1 | escrita |
| T5 | `backend/src/notisbook/files/native_picker.py:1` — docstring cita "Escolher pasta"; prompt agora é "Choose the data directory" | python-engineer | — | 1 | escrita |
| T4 | `frontend/src/components/spark/PrereqsPanel.tsx:1` e `InstallPanel.tsx:2` — docstrings híbridas; voltar ao pt-BR original | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4, T5

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Exemplo usa "Untitled" | `grep -n "Sem título" frontend/src/lib/paths.ts` vazio | refactor |
| T2 | Docstring usa "Untitled" | `grep -n "Sem título" frontend/src/state/workspace.ts` vazio | refactor |
| T3 | Exemplo em inglês | `grep -n "há 5 minutos" frontend/src/components/files/format.ts` vazio | refactor |
| T4 | Docstrings sem frase híbrida | `grep -n "Prerequisites da\|Install version:" frontend/src/components/spark/PrereqsPanel.tsx frontend/src/components/spark/InstallPanel.tsx` vazio | refactor |
| T5 | Docstring alinhada ao prompt | `grep -n "Escolher pasta" backend/src/notisbook/files/native_picker.py` vazio | refactor |

## Arquivos previstos
- `frontend/src/lib/paths.ts` — T1
- `frontend/src/state/workspace.ts` — T2
- `frontend/src/components/files/format.ts` — T3
- `frontend/src/components/spark/PrereqsPanel.tsx` — T4
- `frontend/src/components/spark/InstallPanel.tsx` — T4
- `backend/src/notisbook/files/native_picker.py` — T5

## Fora de escopo
- Tradução geral de comentários pt-BR.
- **Documentação de produto** — nenhuma.

## Não mexer
- Qualquer código executável — só comentários.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->
