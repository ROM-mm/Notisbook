# Pendências cosméticas — painel de variáveis do kernel

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-06 23:59:35 -0300
Modificação: 2026-11-07 00:10:24 -0300
Finalização: —

## Objetivo

Nits do code review do plano painel-variaveis-kernel.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `frontend/src/state/variables.ts:125` — refresh recarrega expandidos com offset 0 e perde páginas de "Show N more…"; guardar quantos itens estavam carregados | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/kernels/introspect.py:199-201` — MAX_PAGE/MAX_DEPTH duplicam MAX_CHILDREN/MAX_PATH_DEPTH; interpolar no source | python-engineer | — | 1 | escrita |
| T3 | `backend/src/notisbook/api/variables.py:21` — `op: Any` em `_snapshot`; tipar como `VarOp` | python-engineer | — | 1 | escrita |
| T4 | `backend/src/notisbook/kernels/introspect.py:269` — namedtuple/OrderedDict/defaultdict/deque caem em object; tratar tipos exatos da stdlib | python-engineer | — | 1 | escrita |
| T5 | `frontend/src/components/variables/VariablesPanel.tsx:191` — refresh descartado com aba oculta; ouvir visibilitychange | python-engineer | — | 1 | escrita |
| T6 | `frontend/src/components/variables/VariablesPanel.tsx:216,234` — pontuação dos hints | python-engineer | — | 1 | escrita |
| T7 | `backend/src/notisbook/kernels/introspect.py:493` — métodos ligados aparecem como `<function ?>`; ler `__func__` nativo e o `__name__` dele | python-engineer | — | 1 | escrita |
| T8 | `backend/src/notisbook/kernels/introspect.py:616` — nome de topo truncado vira path[0] e não expande; devolver `key` completa ou `expandable: false` | python-engineer | — | 1 | escrita |
| T9 | `frontend/src/state/variables.ts:218-219,192` — recolher não poda descendentes; fila relê nós invisíveis | python-engineer | — | 1 | escrita |
| T10 | `backend/src/notisbook/kernels/introspect.py:249` — `_mro` usa `type(obj).__mro__`; trocar por `type.__getattribute__(type(obj), "__mro__")` | python-engineer | — | 1 | escrita |
| T11 | `backend/src/notisbook/kernels/introspect.py:378` — slots privados (`__x`) ficam com nome mangled e somem da árvore; aplicar mangling antes de `_native_get` | python-engineer | — | 1 | escrita |
| T12 | `backend/src/notisbook/kernels/introspect.py:407` — `frozenset()` vazio aparece como `set()`; usar `type(obj).__name__ + "()"` | python-engineer | — | 1 | escrita |
| T13 | `frontend/src/state/variables.ts:180,188,249` — filho em primeiro fetch fica vazio sem nota se `/variables` não volta ok; `toggle` refaz fetch de nó nunca carregado | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Refresh preserva páginas carregadas | `state/variables.ts` guarda contagem carregada por caminho e a usa no refetch | refactor |
| T2 | Limites com fonte única | `grep -n "MAX_PAGE\|MAX_DEPTH" backend/src/notisbook/kernels/introspect.py` → só interpolados | refactor |
| T3 | `_snapshot` tipado | `grep -n "op: VarOp" backend/src/notisbook/api/variables.py` → 1 | refactor |
| T4 | Coleções da stdlib expandem | `introspect.py` trata OrderedDict/defaultdict/deque/namedtuple por tipo exato | feature |
| T5 | Refresh pendente ao voltar a aba | `grep -n visibilitychange frontend/src` → listener no painel/store | bugfix |
| T6 | Hints com pontuação padronizada | hints em `VariablesPanel.tsx` terminam igual | refactor |
| T7 | Métodos ligados com nome | `introspect.py` trata `types.MethodType` via `__func__` | bugfix |
| T8 | Nome longo não quebra expansão | item de topo traz `key` completa ou `expandable: false` quando truncado | bugfix |
| T9 | Recolher poda descendentes ou fila ignora invisíveis | `state/variables.ts` filtra `childQueue` por ancestrais expandidos | refactor |
| T10 | MRO sem passar pela metaclasse | `grep -n "type.__getattribute__(type(obj), \"__mro__\")" introspect.py` → 1 | refactor |
| T11 | Slots privados aparecem | `introspect.py` faz mangling `_Cls__x` para slots `__x` | bugfix |
| T12 | frozenset vazio com rótulo certo | `_d_set` usa `type(obj).__name__ + "()"` | bugfix |
| T13 | Nó nunca carregado refaz fetch ao expandir | `toggle` em `state/variables.ts` refaz quando `items.length === 0 && total === 0 && !loading` | bugfix |

## Arquivos previstos
- `frontend/src/state/variables.ts` — T1, T5
- `backend/src/notisbook/kernels/introspect.py` — T2, T4
- `backend/src/notisbook/api/variables.py` — T3
- `frontend/src/components/variables/VariablesPanel.tsx` — T5, T6

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Protocolo WebSocket v1 e comportamento do Catálogo.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5  - [ ] T6  - [ ] T7  - [ ] T8  - [ ] T9  - [ ] T10  - [ ] T11  - [ ] T12  - [ ] T13

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T10 resolvido (_mro sem metaclasse)
- T13 resolvido (nó cancelado refeito no toggle)
