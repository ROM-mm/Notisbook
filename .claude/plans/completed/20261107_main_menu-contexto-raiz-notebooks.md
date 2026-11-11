# Menu de contexto e escolha da pasta dos notebooks

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-07 01:31:10 -0300
Modificação: 2026-11-07 18:14:14 -0300
Finalização: 2026-11-07 18:14:14 -0300

## Objetivo

No painel Notebooks: (1) botão direito abre menu com Rename e Delete; (2) o `+` escolhe a pasta dos notebooks (vazia ou já com notebooks) pelo seletor nativo do macOS, com fallback de caminho, persistida em `~/.notisbook/preferences.json`; (3) criar notebook fica só no File → New notebook e na home. Como não há autosave e o save grava pelo caminho relativo, apagar/renomear/trocar raiz com aba aberta pode ressuscitar ou sobrescrever arquivos — por isso o backend se defende (409 com kernel ativo; troca de raiz recusada com sessões; token de geração da raiz) e o front fecha as abas antes de trocar. Desenho revisado pelo software-architect.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `DELETE /api/contents/{path}` (204): não resolve o último componente (symlink apaga só o link), pasta recursiva, `.ipynb` como único arquivo aceito, raiz e componente com `.` → 400, ausente → 404, pai fora → 403, caminho sob sessão de kernel ativa → 409 (também no PATCH de rename) | python-engineer | — | 1 | escrita |
| T2 | Menu de contexto no painel Notebooks (reusa `shell/ContextMenu.tsx`) com Rename (edição inline; lápis sai) e Delete (confirmação nomeando o item e, se pasta, "and everything in it"; bloqueado se aberto em aba); 409/500 → mensagem + recarrega | python-engineer | T1 | 1 | escrita |
| T3 | Raiz trocável: `--root` default `None`; precedência `--root` (trava UI) > `preferences.json` (nunca mkdir; inválida → default com aviso) > `~/notebooks`; router `/api/notebooks-root` (token + Host) GET/PUT com validação, lock, escrita atômica, 409 `locked`/`sessions_active`; `/api/fs/places` lê a raiz viva; `choose-dir` ganha `purpose` (`data`/`notebooks`) com prompt constante via argv | python-engineer | T1 | 2 | escrita |
| T4 | Token de geração da raiz: header `X-Notisbook-Root-Generation` enviado pelo front em escritas de `/api/contents` e POST `/api/sessions`; divergência → 409 `root_changed` | python-engineer | T3 | 2 | escrita |
| T5 | `+` do painel: seletor `notebooks` (fallback de caminho) → confirma não salvos → fecha todas as abas (encerra kernels) → PUT → recarrega painel com `browseDir=""`; `+` desabilitado com tooltip quando `locked`; breadcrumb mostra o nome da pasta; botão de criar notebook sai do painel | python-engineer | T3, T4 | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2
- Wave 2 (serial, escrita): T3 → T4 → T5

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | DELETE não resolve o último componente; symlink apaga só o link; raiz e componentes com `.` recusados | `resolve()` segue symlink no último componente e apagaria o alvo; `.` protege `.notisbook`/`.git` se a raiz for ampla | `backend/src/notisbook/notebooks/store.py:98-103` | usar `resolve()` como nas demais rotas |
| D2 | Backend recusa (409) delete/rename sob kernel ativo e troca de raiz com sessões; front fecha abas antes | se o backend matasse kernels, abas abertas salvariam pelo caminho relativo dentro da raiz nova | `backend/src/notisbook/api/sessions.py:56-63`, `backend/src/notisbook/notebooks/store.py:163-172` | backend encerra kernels sozinho |
| D3 | Raiz persistida em `~/.notisbook/preferences.json` (versionado, escrita atômica 0600) | vale já no start, sem depender do navegador | sem evidência — preferência do operador | localStorage |
| D4 | `--root` explícito trava a troca pela UI | com UI liberada, o próximo start com `--root` reverteria em silêncio | `backend/src/notisbook/__main__.py:18` | `--root` só no start |
| D5 | Seletor reaproveita `/api/fs/choose-dir` com enum `purpose`; prompt escolhido no servidor | evita texto arbitrário do cliente em diálogo nativo e rota duplicada | `backend/src/notisbook/files/native_picker.py:19-30` | rota nova; prompt vindo do cliente |
| D6 | Raiz não pode ser `/`, o home do usuário, nem estar dentro de `~/.notisbook` | delete recursivo + raiz ampla = raio de impacto alto | sem evidência — decisão de segurança | permitir `~` |
| D7 | Token de geração da raiz | fecha ressurreição/sobrescrita por aba velha ou segunda janela após troca | parecer do software-architect | só bloqueio no front |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Apaga notebook e pasta recursiva | servidor em `<scratch>` (`--root <scratch>/r`, `NOTISBOOK_HOME=<scratch>/h`): `DELETE /api/contents/a.ipynb` → 204 e arquivo some; `DELETE /api/contents/d` (pasta com conteúdo) → 204 e pasta some | feature |
| T1 | Symlink apaga só o link | `DELETE` de um symlink para pasta externa → 204, link some, alvo intacto | feature |
| T1 | Recusas | `DELETE /api/contents/` e `.../a/..` → 400; componente com `.` → 400; arquivo não-`.ipynb` → 400; inexistente → 404 | constraint |
| T1 | Kernel ativo bloqueia | com sessão criada para `k.ipynb`, `DELETE` e `PATCH` de `k.ipynb` (e da pasta que o contém) → 409; arquivo intacto | constraint |
| T2 | Menu de contexto com Rename e Delete e sem lápis | leitura de `frontend/src/components/files/FileBrowser.tsx`: `onContextMenu` (e tecla ContextMenu) abre `ContextMenu` com itens Rename e Delete (`danger`); nenhum botão de lápis por item; Delete usa `window.confirm` e respeita `isOpenUnder` | feature |
| T2 | Botão direito em qualquer item (notebook ou pasta) seleciona o item — destaque visual próprio de seleção, que permanece enquanto o menu está aberto e depois dele até outro clique, troca de pasta ou Esc — e abre o menu; a seleção é única — ajuste pedido pelo operador no teste do commit d651c95 | leitura de `frontend/src/components/files/FileBrowser.tsx`: estado de item selecionado setado no `onContextMenu` (e na tecla ContextMenu) antes de abrir o menu, com atributo de seleção (ex.: `data-selected`/`aria-selected`) na linha; `FileBrowser.module.css` estiliza o selecionado; clique esquerdo em outro item, troca de `browseDir` e Esc limpam/movem a seleção; `npm run build` → exit 0 | feature |
| T3 | GET/PUT da raiz | `GET /api/notebooks-root` → `{path,name,source,locked,generation}`; servidor sem `--root`: `PUT {path:<scratch>/r2}` → 200, `preferences.json` em `<scratch>/h` com o caminho, `GET /api/contents` lista `<scratch>/r2` | feature |
| T3 | Validação e travas | `PUT` com relativo/`/`/home/dentro de `<scratch>/h` → 400; inexistente → 404; com sessão ativa → 409 `sessions_active` (raiz e arquivo inalterados); servidor com `--root` → 409 `locked` | constraint |
| T3 | Precedência no start | reiniciar sem `--root` → raiz = salva; `preferences.json` apontando para pasta inexistente → raiz = `default_root()` com aviso em stderr e a pasta inexistente NÃO é criada | feature |
| T3 | Seletor com `purpose` | `git grep -n "Choose the notebooks folder" -- backend/src` → 1 ocorrência; o script AppleScript continua constante (prompt via argv) | feature |
| T3 | `/api/fs/places` usa a raiz viva | após `PUT`, `GET /api/fs/places` traz o atalho Notebooks apontando para a nova raiz | bugfix |
| T4 | Geração divergente é recusada | `PUT /api/contents/x.ipynb` com `X-Notisbook-Root-Generation` antigo → 409 `root_changed`; com o atual → 200 | constraint |
| T5 | Fluxo do `+` | leitura de `FileBrowser.tsx` + `state/workspace.ts`: `+` chama o seletor `notebooks` (fallback de caminho), confirma não salvos, fecha todas as abas, faz PUT, zera `browseDir`; desabilitado com tooltip se `locked`; breadcrumb exibe o nome da pasta; não há botão de criar notebook no painel | feature |
| T3 | Raiz não pode ser ancestral do home nem de `~/.notisbook`; `delete` recusa alvo que contenha o home ou `~/.notisbook` (defesa em profundidade, cobre `--root`) — achado major do review, rodada 1 | servidor de teste com `HOME=<scratch>/fakehome`: `PUT` com o pai do fakehome → 400; servidor com `--root` = pai do fakehome: `DELETE` do fakehome → 400 e fakehome intacto | bugfix |
| T1 | Checagem de sessão segura com kernel nascendo e por caminho real (alias/symlink): sem `RuntimeError` por iteração concorrente; sessão aberta por symlink de pasta bloqueia delete/rename da pasta real (409) — achados minor do review, rodada 1 | leitura: handlers de delete/rename/put_root fazem a checagem no event loop (handler `async` + I/O em threadpool) ou sobre snapshot; sessão guarda caminho resolvido; servidor de teste: sessão em `alias/x.ipynb` (alias → `real`) → `DELETE real` → 409 | bugfix |
| T3 | Criação de sessão após troca de raiz não inicia na raiz antiga — achado minor do review, rodada 1 | leitura de `api/sessions.py`/`notebooks_root.py`: criação de sessão e troca de raiz serializadas por lock comum ou geração rechecada após `kernels.create` | bugfix |
| T3 | Validação de raiz é uma função pura reaplicada no start à preferência salva e exposta em `PUT /api/notebooks-root?dry_run=true` (valida sem trocar nem persistir, sem checar sessões) — achado minor do review, rodada 1 | `preferences.json` com `"/"` → start cai no default com aviso; `PUT ?dry_run=true` com caminho válido → 200 e raiz/arquivo inalterados; com o home → 400 | bugfix |
| T5 | O `+` valida (`dry_run`) antes de fechar abas; caminho recusado não fecha nada — achado minor do review, rodada 1 | leitura de `FileBrowser.tsx`: `dry_run` precede `closeAllTabs` e o PUT real | bugfix |
| T4 | Geração carregada no bootstrap do app (após `bootstrapAuth`), independente do painel — achado minor do review, rodada 1 | leitura de `frontend/src/App.tsx`: carga da raiz/geração junto ao bootstrap, antes de liberar `ready`; efeito de carga do `FileBrowser` removido | bugfix |
| T4 | `root_changed`, `sessions_active` e `locked` têm texto amigável em qualquer fluxo — achado minor do review, rodada 1 | leitura do mapeamento central de erros em `frontend/src/api/http.ts` | bugfix |
| T5 | Frontend compila | `cd frontend && npm run build` → exit 0 | constraint |

## Arquivos previstos
- `backend/src/notisbook/notebooks/store.py` — T1
- `backend/src/notisbook/api/contents.py` — T1, T4
- `backend/src/notisbook/kernels/service.py` — T1
- `frontend/src/components/files/FileBrowser.tsx` — T2, T5
- `frontend/src/components/files/FileBrowser.module.css` — T2, T5
- `frontend/src/api/contents.ts` — T2
- `backend/src/notisbook/__main__.py` — T3
- `backend/src/notisbook/config.py` — T3
- `backend/src/notisbook/preferences.py` — T3
- `backend/src/notisbook/api/notebooks_root.py` — T3
- `backend/src/notisbook/app.py` — T3
- `backend/src/notisbook/api/files.py` — T3
- `backend/src/notisbook/files/native_picker.py` — T3
- `backend/src/notisbook/api/sessions.py` — T4
- `frontend/src/api/http.ts` — T4
- `frontend/src/api/notebooksRoot.ts` — T5
- `frontend/src/api/files.ts` — T5
- `frontend/src/state/workspace.ts` — T5
- `frontend/src/App.tsx` — T4

## Fora de escopo
- Lixeira do macOS / desfazer exclusão; várias raízes ou recentes; mover notebooks entre raízes; observar o disco; autosave.
- Seletor nativo fora do macOS (segue o fallback de caminho).
- **Documentação de produto** — nenhuma (o repo não tem README nem `docs/`). ADR recomendada pelo software-architect não é escrita aqui; só sob pedido.

## Não mexer
- Painel Data: comportamento e prompt do seu `+` (`purpose` padrão `data`).
- File → New notebook (`frontend/src/components/shell/Topbar.tsx`) e botão da home.
- Filtro de entradas `file` do painel e a regra de nomes livres sobre a listagem completa.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 107203 | 75218 |
| 0 | software-architect | OK | 129654 | 50165 |
| 1 | python-engineer | OK | 82970 | 54868 |
| 2 | python-engineer | OK | 217104 | 87331 |
| 2 | code-review | ajustes necessários | 134326 | 87105 |
| 2 | plan-auditor | CONFORME | 44229 | 34817 |
| 2 | python-engineer | OK | 198167 | 82290 |
| 2 | code-review | aprovar | 129352 | 95552 |
| 2 | plan-auditor | CONFORME | 64676 | 41028 |
| 3 | python-engineer | OK | 30689 | 34073 |
| 3 | code-review | aprovar | 49754 | 62471 |
| 3 | plan-auditor | CONFORME | 42489 | 32962 |
<!-- effort-ledger:end -->
