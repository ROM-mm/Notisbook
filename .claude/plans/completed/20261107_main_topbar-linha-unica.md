# Topbar do notebook em linha única

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-07 00:17:45 -0300
Modificação: 2026-11-07 00:29:18 -0300
Finalização: 2026-11-07 00:29:18 -0300

## Objetivo

A topbar do notebook aberto vira UMA linha: menu `File … Settings` à esquerda e, à direita, `● Idle` → seletor do Spark → toggle Variables. Sai o título (e a bolinha de dirty), que a aba já mostra, e sai o texto "Unsaved"/"Saved"; o indicador de save fica só para `Saving…` e `Save failed` (o erro de save não tem outro lugar na tela).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Topbar do notebook em linha única, sem título/dirty dot/"Unsaved" | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Notebook aberto não renderiza título nem dirty dot na topbar | `grep -n 'notebook-title\|dirtyDot' frontend/src/components/shell/Topbar.tsx` → nenhuma ocorrência | feature |
| T1 | Menu e ações à direita na mesma linha, ordem KernelStatus → KernelSelector → VariablesToggle | leitura de `Topbar.tsx`: com `entry`, um único container de linha contém `MenuBar` e, à direita, `<KernelStatus />`, `<KernelSelector />`, `<VariablesToggle />` nessa ordem; no app, a topbar mostra uma linha só | feature |
| T1 | "Unsaved"/"Saved" não aparecem; `Saving…` e `Save failed` continuam | `grep -n '"Unsaved"\|"Saved"' frontend/src/components/shell/Topbar.tsx` → nenhuma ocorrência; `grep -n 'Save failed' frontend/src/components/shell/Topbar.tsx` → presente | feature |
| T1 | Lista do seletor de ambiente abre para a esquerda na topbar (ancorada à direita), sem passar da borda da viewport — achado major do review, rodada 1 | `AppShell.module.css` tem regra escopada à topbar que aplica `left: auto; right: 0` à lista do seletor (ex.: `[data-testid="kernel-selector-list"]` dentro do grupo de ações); `Kernel.module.css` sem alteração (`git diff 778adf0 -- frontend/src/components/kernel` vazio) | bugfix |
| T1 | Linha única encolhe sem estourar na horizontal (menubar com `min-width: 0` e/ou seletor podendo encolher) — achado minor do review, rodada 1 | leitura de `AppShell.module.css`: o menubar ou o seletor no grupo de ações tem `min-width: 0` e encolhimento permitido (`flex-shrink`/`overflow-x`) | bugfix |
| T1 | Frontend compila e lint passa | `cd frontend && npm run build` (e `npm run lint` se existir) → exit 0 | constraint |

## Arquivos previstos
- `frontend/src/components/shell/Topbar.tsx` — T1
- `frontend/src/components/shell/AppShell.module.css` — T1

## Fora de escopo
- Topbar sem notebook (ramo `title` de `Topbar`) — fica como está.
- **Documentação de produto** — nenhuma.

## Não mexer
- `TabBar.tsx` (aba com nome e dirty dot) e os componentes `KernelSelector`/`KernelStatus` por dentro.
- Itens e comportamento do `MenuBar`.

## Status
- [x] T1

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 30852 | 34596 |
| 1 | code-review | ajustes necessários | 59907 | 62310 |
| 1 | plan-auditor | CONFORME | 30891 | 22540 |
| 1 | python-engineer | OK | 149564 | 32491 |
| 1 | code-review | aprovar | 54529 | 61833 |
| 1 | plan-auditor | CONFORME | 37558 | 23742 |
<!-- effort-ledger:end -->
