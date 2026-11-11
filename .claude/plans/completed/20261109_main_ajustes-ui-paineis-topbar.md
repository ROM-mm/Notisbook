# Ajustes de UI: caminho do FILES, About, painéis redimensionáveis e recursos na topbar

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-09 11:21:46 -0300
Modificação: 2026-11-09 11:40:39 -0300
Finalização: 2026-11-09 11:40:39 -0300

## Objetivo

Cinco ajustes de UI pedidos pelo operador, na ordem estética → comportamento → recursos: remover a caixa do caminho no painel FILES; trocar o botão Settings por um item de menu "About" que abre um diálogo com a marca + "Notisbook" / "Romerito Morais"; tornar arrastáveis com o mouse as bordas verticais do painel lateral e do painel Variables e a divisória horizontal Catalog/Files (tamanhos só em memória — reset ao fechar o app); mostrar RAM/CPU/disco da máquina no espaço vazio da topbar, servido por um endpoint novo com psutil.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Remover a caixa do caminho raiz do painel FILES | python-engineer | — | 1 | escrita |
| T2 | Botão Settings → item "About" abrindo diálogo com BrandMark + Notisbook/Romerito Morais | python-engineer | — | 1 | escrita |
| T3 | Bordas verticais arrastáveis: painel lateral (direita) e Variables (esquerda), larguras em memória | python-engineer | — | 2 | escrita |
| T4 | Divisória horizontal Catalog/Files arrastável, proporção em memória | python-engineer | — | 2 | escrita |
| T5 | GET /api/system/resources com psutil | python-engineer | — | 3 | escrita |
| T6 | Widget de recursos na topbar com polling | python-engineer | T5 | 3 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2
- Wave 2 (serial, escrita): T3, T4
- Wave 3 (serial, escrita): T5, T6

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | psutil como dependência nova do backend | RAM usada no macOS sem psutil exige sysctl/vm_stat por subprocesso, frágil | parecer software-architect; psutil ausente de backend/pyproject.toml e uv.lock | stdlib + sysctl/vm_stat (descartada: frágil, só macOS) |
| D2 | Contrato `{memory:{used,total}, cpu:{percent,cores}, disk:{used,total}}` em bytes/percentual, `null` por métrica em falha; formatação só no front | backend não formata; sem caminho de volume no JSON | parecer software-architect | backend devolver strings formatadas |
| D3 | Rota com require_token + require_trusted_host, handler síncrono | dado identifica a máquina; padrão dos routers que tocam o host; def roda em threadpool | backend/src/notisbook/api/files.py, security.py:44 | só require_token |
| D4 | RAM usada = total − available (1024³); disco = volume da pasta raiz dos notebooks, used = total − free (1000³) | `used` do psutil no macOS/APFS engana | parecer software-architect (unverified no Context7) | disk_usage("/") e campo used |
| D5 | CPU como "núcleos em uso/total" (percent×cores/100), % no tooltip | mantém o formato X/Y pedido | sem evidência — preferência do operador ("o mesmo para CPU") | "CPU 23%" |
| D6 | Polling 5 s com setTimeout encadeado, só após bootstrapAuth ok, pausa com aba oculta, 30 s após 3 falhas, sem toast | evita sobreposição e request antes do auth | frontend/src/api/auth.ts; memória requests-de-api-so-depois-do-bootstrap-auth | setInterval; rota separada para disco |
| D7 | Tamanhos de painéis em estado zustand sem persist | operador pediu reset ao fechar o app | sem evidência — pedido do operador | localStorage |
| D8 | Settings sai da topbar; página de ambientes segue acessível por "Manage environments…" | duplicidade: ambos chamam openSettings() | frontend/src/components/kernel/KernelSelector.tsx:130-134 | manter Settings ao lado do About |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Caixa do caminho removida do FILES | `grep -rn 'files-root-path\|styles.pathText' frontend/src` sem resultados | feature |
| T1 | Caminho raiz segue usado na árvore, copiar caminho e seletor de pasta | `grep -n 'root' frontend/src/components/data/FilesSection.tsx` mostra `chooseDirectory(root)` e `initialPath={root}` | constraint |
| T2 | Topbar sem botão Settings; diálogo About com BrandMark e textos "Notisbook"/"Romerito Morais" (botão: ver linha "teste do operador") | `grep -n 'Settings' frontend/src/components/shell/Topbar.tsx` sem botão; `grep -rn 'Romerito Morais' frontend/src` encontra `AboutDialog.tsx` | feature |
| T2 | Clique em About abre `<dialog>` modal About | `grep -rn 'showModal' frontend/src/components/shell/AboutDialog.tsx` | feature |
| T3 | Painel lateral e Variables com alça de arraste horizontal, largura limitada por mín/máx | `grep -rn 'col-resize' frontend/src` e uso de pointer events no componente de alça | feature |
| T3 | Larguras não persistem entre execuções | `grep -rn 'persist\|localStorage' frontend/src/state/layout.ts` sem resultados | constraint |
| T4 | Divisória Catalog/Files arrastável na vertical, respeitando altura mínima | `grep -n 'orientation="horizontal"' frontend/src/components/data/DataPanel.tsx` (alça `ResizeHandle`; cursor row-resize em `ResizeHandle.tsx`) — verificação ajustada no refino pós-wave 2 | feature |
| T5 | GET /api/system/resources devolve o contrato D2 com require_token + require_trusted_host | `grep -n 'system/resources\|require_trusted_host' backend/src/notisbook/api/system.py` | feature |
| T5 | psutil declarado e travado | `grep -n psutil backend/pyproject.toml backend/uv.lock` | feature |
| T6 | Topbar mostra "RAM x/y GB · CPU x/y · Disk x/y GB" antes de KernelStatus | `grep -n 'SystemResources' frontend/src/components/shell/Topbar.tsx` | feature |
| T6 | Polling só após bootstrapAuth, setTimeout encadeado, pausa em visibilitychange | `grep -n 'visibilitychange\|setTimeout' frontend/src/state/systemResources.ts` | feature |
| T3 | Comentário do ResizeHandle sem referência ao código anterior (review rodada 1) | `grep -n 'antiga' frontend/src/components/shell/ResizeHandle.tsx` sem resultados | constraint |
| T2 | Clique no padding/conteúdo do About não fecha o diálogo; só o backdrop fecha (review rodada 1) | `frontend/src/components/shell/AboutDialog.tsx`: padding do `<dialog>` zerado com conteúdo em `<div>` interno, ou checagem por `getBoundingClientRect` no handler de clique | bugfix |
| T2 | Botão da topbar mostra só o texto "About", no estilo dos demais itens do menu; ícone e "Notisbook"/"Romerito Morais" ficam só no diálogo (teste do operador) | `grep -n 'Romerito Morais\|BrandMark' frontend/src/components/shell/Topbar.tsx` sem resultados e `grep -n '>About<' frontend/src/components/shell/Topbar.tsx` encontra o botão | bugfix |
| T1–T6 | Frontend compila | `cd frontend && npm run typecheck` sai 0 | constraint |
| T5 | Backend sem erro de lint nos arquivos tocados | `cd backend && ruff check src/notisbook/api/system.py` sai 0 — verificação ajustada após auditoria rodada 1: app.py não foi tocado e o I001 nele é pré-existente no baseline | constraint |

## Arquivos previstos
- `frontend/src/components/data/FilesSection.tsx` — T1
- `frontend/src/components/data/DataPanel.module.css` — T1, T4
- `frontend/src/components/data/DataPanel.tsx` — T4
- `frontend/src/components/shell/Topbar.tsx` — T2, T6
- `frontend/src/components/shell/AboutDialog.tsx` — T2
- `frontend/src/components/shell/AppShell.tsx` — T2, T3
- `frontend/src/components/shell/AppShell.module.css` — T2, T3, T6
- `frontend/src/state/workspace.ts` — T2
- `frontend/src/state/router.ts` — T2
- `frontend/src/components/shell/ResizeHandle.tsx` — T3, T4
- `frontend/src/state/layout.ts` — T3, T4
- `frontend/src/components/variables/VariablesPanel.tsx` — T3
- `frontend/src/components/variables/VariablesPanel.module.css` — T3
- `frontend/src/components/shell/SystemResources.tsx` — T6
- `frontend/src/state/systemResources.ts` — T6
- `frontend/src/api/system.ts` — T6
- `frontend/src/api/index.ts` — T6
- `frontend/src/App.tsx` — T2, T6
- `backend/src/notisbook/api/system.py` — T5
- `backend/src/notisbook/app.py` — T5
- `backend/pyproject.toml` — T5
- `backend/uv.lock` — T5

## Fora de escopo
- Criação de testes — não pedida pelo operador.
- Resize por teclado — operador pediu arraste com mouse.
- **Documentação de produto** — README/ARCHITECTURE podem ficar sem menção ao endpoint de recursos e ao About. Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- `frontend/src/components/settings/SettingsPage.tsx` e a rota `/settings` — continuam acessíveis por "Manage environments…".
- `frontend/src/state/files.ts` — persistência de `notisbook.files.root` intacta.
- Demais rotas de `backend/src/notisbook/api/` além de `system.py`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| - | knowledge-engineer | OK | 89499 | 62730 |
| - | software-architect | OK | 44051 | 24715 |
| 1 | python-engineer | OK | 35020 | 39829 |
| 2 | python-engineer | OK | 77991 | 43098 |
| 3 | python-engineer | OK | 54702 | 41471 |
| - | plan-auditor | OK | 38014 | 25846 |
| - | code-review | ajustes necessários | 73934 | 78530 |
| loop-1 | python-engineer | OK | 17989 | 27647 |
| loop-1 | code-review | aprovar | 51960 | 78838 |
| loop-1 | plan-auditor | CONFORME | 30450 | 25919 |
| loop-2 | python-engineer | OK | 20002 | 28943 |
| loop-2 | code-review | aprovar | 163077 | 76883 |
| loop-2 | plan-auditor | CONFORME | 37399 | 25339 |
| - | memory-manager | OK | 17887 | 50874 |
<!-- effort-ledger:end -->
