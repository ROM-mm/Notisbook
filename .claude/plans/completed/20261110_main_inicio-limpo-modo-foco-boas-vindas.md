# Tela inicial limpa + modo foco + boas-vindas "Spark it up locally."

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 23:27:54 -0300
Modificação: 2026-11-10 23:38:33 -0300
Finalização: 2026-11-10 23:38:33 -0300

## Objetivo

Ao abrir o app não aparece nada à esquerda (nem o rail, nem o painel) — só a boas-vindas nova. "Open Notebooks panel" mostra o rail e abre o painel Notebooks; "New notebook" cria o notebook e também abre o painel. Um modo foco (`Cmd+.`, View → Focus mode, botão na topbar) esconde rail + painel lateral + Variables, deixando só as células. Boas-vindas: título "Spark it up locally." em fonte script com marca-texto amarelo pastel, subtítulo "Iceberg, Delta, Hudi & Parquet — on your laptop.", fileira de 4 ícones próprios com o nome do formato.

Mapa do código (levantamento read-only): estado em zustand só em memória — `useWorkspace.panel` default `"notebooks"` (`frontend/src/state/workspace.ts:96`); rail sempre renderizado (`frontend/src/components/shell/AppShell.tsx:40`); `.body` é flex; estado vazio em `Home()` (`frontend/src/App.tsx:72-96`); `createUntitledNotebook` não abre painel (`state/workspace.ts:169-185`); menus em `components/shell/Topbar.tsx` (`viewItems` :115); sem registro central de atalhos; lista fixa em `components/shell/ShortcutsDialog.tsx:8-18`; nenhum conflito com Cmd+.; nenhum teste no repo.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Início limpo: painel começa fechado; rail só aparece depois que algum painel é aberto (botão, New notebook, deep link /tree/…) | python-engineer | — | 1 | escrita |
| T2 | Modo foco: esconde rail + painel lateral + Variables; Cmd+. (inclusive dentro do editor), View → Focus mode com ✓, botão na topbar; atalho na lista de atalhos | python-engineer | T1 | 2 | escrita |
| T3 | Boas-vindas nova: título script "Spark it up locally." com marca-texto amarelo, subtítulo, 4 ícones próprios (Iceberg, Delta, Hudi, Parquet) com nome, botões mantidos | python-engineer | T1 | 3 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1
- Wave 2 (serial, escrita): T2
- Wave 3 (serial, escrita): T3

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Estado de rail/foco só em memória; recarregar volta ao início limpo | operador: "isso apenas no início"; padrão atual do store | `state/layout.ts:1-4`, `state/workspace.ts` | persistir em localStorage |
| D2 | Ícones próprios no traço do app (Iceberg e Hudi novos; Parquet e Delta reaproveitados) | operador escolheu (b); evita marcas de terceiros | `components/shell/icons.tsx:156,183` | logos oficiais |
| D3 | Fonte script Pacifico via `@fontsource/pacifico` (subset latin) | app offline; mesmo padrão das demais fontes | `frontend/src/main.tsx:6-15` | Google Fonts CDN |
| D4 | Cmd+. tratado num listener global no AppShell | precisa funcionar sem notebook aberto; não há registro central | `NotebookView.tsx:108` só com notebook | listener no NotebookView |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Build sem erro | `cd frontend && npm run build` → exit 0 | constraint |
| T1 | Typecheck limpo | `cd frontend && npm run typecheck` → exit 0 | constraint |
| T1 | Painel não começa aberto | `grep -n 'panel: "notebooks"' frontend/src/state/workspace.ts` → sem saída | feature |
| T1 | Rail condicional | `grep -n "<Sidebar" -B2 frontend/src/components/shell/AppShell.tsx` → renderização condicionada a estado | feature |
| T2 | Item de menu do modo foco | `grep -n "Focus mode" frontend/src/components/shell/Topbar.tsx` → presente | feature |
| T2 | Atalho documentado | `grep -n "⌘\.\|Cmd+\.\|Mod-\." frontend/src/components/shell/ShortcutsDialog.tsx` → presente | feature |
| T3 | Título novo | `grep -n "Spark it up locally." frontend/src/App.tsx` → presente | feature |
| T3 | Fonte empacotada | `grep -n "@fontsource/pacifico" frontend/src/main.tsx frontend/package.json` → presentes | feature |
| T3 | Ícones próprios | `grep -nE "IcebergIcon|HudiIcon" frontend/src/components/shell/icons.tsx` → presentes | feature |
| T3 | Sem canto arredondado | `grep -rnE "border-radius:\s*[^0;]" frontend/src` → sem saída | constraint |
| T2 | (review r1) Abrir painel sai do modo foco | em `state/workspace.ts`, `setPanel`/`togglePanel`/`setRightPanel`/`toggleRightPanel` com destino não-nulo gravam `focusMode: false` | fix |
| T2 | (review r1) Atalho ignora tecla repetida | `grep -n "e.repeat" frontend/src/components/shell/AppShell.tsx` → presente | fix |
| T3 | (review r1) Título legível fora da faixa no escuro | `.homeMark` em `AppShell.module.css`: faixa cobre a caixa do texto e/ou cor fora da faixa com contraste nos dois temas | fix |
| T2 | (review r2) Toggle de Variables coerente com o foco | `VariablesToggle` em `Topbar.tsx` lê `focusMode` para `aria-pressed`; `toggleRightPanel` em `workspace.ts` reabre (e sai do foco) quando o painel já está aberto mas oculto pelo foco | fix |
| T1 | Nada fora do escopo mudou | `git diff --stat <baseline> -- frontend/src/api frontend/src/ws frontend/src/lib backend` → vazio | constraint |

## Arquivos previstos
- `frontend/src/state/workspace.ts` — T1, T2
- `frontend/src/App.tsx` — T1, T3
- `frontend/src/components/shell/AppShell.tsx` — T1, T2
- `frontend/src/components/shell/AppShell.module.css` — T1, T2, T3
- `frontend/src/components/shell/Sidebar.tsx` — T1 (só se necessário)
- `frontend/src/components/shell/Topbar.tsx` — T2
- `frontend/src/components/shell/ShortcutsDialog.tsx` — T2
- `frontend/src/components/shell/icons.tsx` — T3
- `frontend/src/main.tsx` — T3
- `frontend/package.json` — T3
- `frontend/package-lock.json` — T3
- `frontend/src/styles/tokens.css` — T3

## Fora de escopo
- Pendências cosméticas já registradas (`.claude/plans/pendencias/`).
- Painel direito Variables fora do modo foco.
- **Documentação de produto** — nenhuma.

## Não mexer
- Formato do `.ipynb`, kernels, `backend/**`, `frontend/src/api/**`, `frontend/src/ws/**`, `frontend/src/lib/**`.
- Atalhos existentes e textos do resto da interface.

## Status
- [x] T1  - [x] T2  - [x] T3

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1-3 | python-engineer (T1-T3) | OK | 74953 | 60297 |
| 2-3 | python-engineer (review r1) | OK | 22935 | 30353 |
| 2 | python-engineer (review r2) | OK | 24278 | 31272 |
<!-- effort-ledger:end -->
