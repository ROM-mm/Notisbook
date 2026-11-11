# Bibliotecas por ambiente Spark + Remove limpo

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-09 12:56:04 -0300
Modificação: 2026-11-09 13:37:55 -0300
Finalização: 2026-11-09 13:37:55 -0300

## Objetivo

Hoje não dá para adicionar/remover/atualizar libs Python de um ambiente Spark instalado sem ir ao terminal, e o Remove do ambiente deixa sobras (pastas `spark-<v>-*` de reinstalação e `rmtree` falho que ainda responde 204). Cada ambiente instalado ganha um botão **Config** (ao lado do Remove) que abre um modal bloqueante: lista todas as libs do ambiente (base incluída), toolbar **＋ − ↑** (adicionar; desinstalar as marcadas; atualizar as marcadas para a última), seleção múltipla, só PyPI. O Remove do ambiente passa a não deixar nada daquele ambiente para trás. Mockups aprovados: `.claude/plans/mockups/libs-por-ambiente-spark/` (`page.png`, `config2.png`, `add2.png`, `progress.png`, `done.png`).

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Dependência `packaging` + validação de nome PEP 508 e spec PEP 440 (`spark/requirements.py`) e `core_names(version)` | python-engineer | — | 1 | escrita |
| T2 | Lock por kernel com `kind` (install/packages) compartilhado por install, libs e remove; runner de comando extraído sem `PHASES.index` | python-engineer | — | 2 | escrita |
| T3 | Remove limpo: kernelspec falho vira erro, todas as `spark-<v>-<hex8>` → trash → rmtree, 500 com sobras, `sweep_trash()` no start e antes de install | python-engineer | T2 | 3 | escrita |
| T4 | Endpoints de libs (list / add / upgrade em lote / uninstall em lote) como jobs, PyPI-only | python-engineer | T1,T2 | 4 | escrita |
| T5 | Bloquear criação de sessão enquanto houver job de libs no kernel | python-engineer | T2 | 5 | escrita |
| T6 | Tipos e cliente da API no front; reattach só de jobs `kind: install` em `useSparkData` | python-engineer | T3,T4 | 6 | escrita |
| T7 | `PackagesDialog` (toolbar ＋ − ↑, filtro, seleção múltipla, selo core, travado durante job, faixa de resultado + View log, destaque/selo new), `AddLibraryDialog`, `usePackages`, `JobProgress` reutilizável | python-engineer | T6 | 7 | escrita |
| T8 | Botão Config na linha do ambiente, motivos de bloqueio, mensagem de sobra no Remove | python-engineer | T7 | 8 | escrita |

## Ordem de execução (waves)
- Waves 1–8 (serial, escrita): T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Libs alteradas in-place com `uv pip --python <env>/bin/python` | simples e rápido; requisito direto | `spark/installer.py:159-160` usa `uv pip install --python` | copiar o env a cada mudança (centenas de MB) |
| D2 | 409 com sessão aberta no kernel ou job ativo; nova sessão recusada durante job de libs | kernel vivo importaria pacote meio instalado | `api/spark.py:84-85,98-99`; `api/sessions.py:55-75` não checa lock | permitir com sessão aberta |
| D3 | PyPI-only: nome/spec validados (sem URL/path/git/`@`/`;`/extras), `--no-config`, `--default-index` = `NOTISBOOK_PYPI_URL`/simple, env sem `UV_*` (allowlist) | entrada do usuário nunca define origem | `config.py:45-55` (`NOTISBOOK_PYPI_URL`) | regex à mão no lugar de `packaging`; `--only-binary` |
| D4 | Remove apaga kernelspec + todas as pastas do ambiente; mantém `warehouse/`, `metastore/`, `duckdb/extensions`, cache do uv | dados compartilhados entre versões | `installer.py:318-343`; `bundles.py:152-182`; `kernels/service.py:557` | apagar warehouse/metastore (perda de dados das outras versões) |
| D5 | ~~Libs core com selo e confirmação, sem bloqueio~~ → **revisada após teste do operador:** libs core (pyspark, py4j, ipykernel, duckdb + pip do bundle) ficam OCULTAS da lista, recusadas (422) em add/upgrade/uninstall e fixadas na versão atual em toda instalação | trocar só uma delas quebra o ambiente; ou se troca o ambiente inteiro (Remove + Install) ou nada | teste manual do operador em 8cada89 (pyspark 3.5.9 listado e desinstalável) | mostrar com selo e confirmação (versão anterior); bloquear só na UI |
| D6 | Add de lib existente → `-P <nome>` (vai à maior versão permitida pela spec) | requisito "se existir, atualiza" | sem evidência — preferência do operador | ignorar libs já instaladas |
| D7 | Upgrade e uninstall em lote (lista de nomes), toolbar no topo | seleção múltipla pedida pelo operador | sem evidência — preferência do operador | ação por linha via menu ⋯ |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `packaging` declarado no backend | `grep -n packaging backend/pyproject.toml` ≥ 1 | feature |
| T1 | Spec normalizada e entradas inseguras recusadas | `cd backend && uv run python -c "from notisbook.spark.requirements import parse_requirement as p; print(p('Delta_Spark','>=2.0,<3'))"` imprime `delta-spark` + as cláusulas `<3` e `>=2.0`; `p('x','@ https://a')` e `p('-e','')` levantam `ValueError` | feature |
| T2 | Lock com tipo exposto | `grep -nE "def (try_acquire|release|is_mutating)" backend/src/notisbook/spark/installer.py` = 3; `grep -n '"kind"' backend/src/notisbook/api/spark.py` ≥ 1 | feature |
| T3 | Falha de kernelspec não é mais silenciosa | `grep -n "ignore_errors=True" backend/src/notisbook/spark/kernelspec.py` = 0 | bugfix |
| T3 | Sobras viram erro e são varridas | `grep -n "sweep_trash" backend/src/notisbook/app.py backend/src/notisbook/spark/installer.py` ≥ 3; `grep -n "HTTPException(500\|status_code=500" backend/src/notisbook/api/spark.py` ≥ 1 | bugfix |
| T4 | Quatro rotas de libs | `grep -nE '"/versions/\{version\}/packages(/upgrade|/uninstall)?"' backend/src/notisbook/api/spark.py` = 4 | feature |
| T4 | Comandos PyPI-only e env sem `UV_*` | `grep -nE -- "--no-config|--default-index" backend/src/notisbook/spark/packages.py` ≥ 2; `grep -n 'startswith("UV_")' backend/src/notisbook/spark/packages.py` ≥ 1 | constraint |
| T4 | Upgrade/uninstall aceitam lista de nomes numa só chamada de `uv` | `grep -n "names: list\[str\]\|names: List\[str\]" backend/src/notisbook/api/spark.py` ≥ 1; `grep -n '"uninstall"' backend/src/notisbook/spark/packages.py` ≥ 1 | feature |
| T5 | Sessão recusada durante job de libs | `grep -n "is_mutating" backend/src/notisbook/api/sessions.py` ≥ 1, em linha anterior a `kernels.create` | feature |
| T6 | Cliente da API de libs | `grep -cE "export (async )?function (listPackages|addPackages|upgradePackages|uninstallPackages)" frontend/src/api/spark.ts` = 4; `cd frontend && npm run typecheck` exit 0 | feature |
| T7 | Modal bloqueante com toolbar e seleção múltipla | `grep -n "showModal" frontend/src/components/spark/PackagesDialog.tsx` ≥ 1; `grep -n "onCancel" frontend/src/components/spark/PackagesDialog.tsx` ≥ 1; `grep -nE 'aria-label="(Add libraries|Uninstall selected|Upgrade selected)"' frontend/src/components/spark/PackagesDialog.tsx` = 3; `grep -n "Set<string>" frontend/src/components/spark/PackagesDialog.tsx` ≥ 1 | feature |
| T7 | Nome repetido bloqueado no Add | `grep -n "already in the list" frontend/src/components/spark/AddLibraryDialog.tsx` ≥ 1 | feature |
| T8 | Config na linha do ambiente e build ok | `grep -n "spark-version-config" frontend/src/components/spark/InstalledList.tsx` ≥ 1; `cd frontend && npm run build` exit 0 | feature |
| T3 | Varredura da lixeira dentro do install restrita à própria versão (review rodada 1) | `grep -nE "sweep_trash\([a-z_.]+\)" backend/src/notisbook/spark/installer.py` ≥ 1 | bugfix |
| T3 | rmtree incompleto vira sobra reportada, não sucesso (review rodada 1) | `grep -n "doomed.exists()" backend/src/notisbook/spark/installer.py` ≥ 1 | bugfix |
| T7 | Modal travado também durante o POST pendente; attach ignorado após unmount (review rodada 1) | `grep -n "pending" frontend/src/components/spark/usePackages.ts` ≥ 1; `grep -n "mounted.current" frontend/src/components/spark/usePackages.ts` ≥ 1 | bugfix |
| T7 | Reattach usa a ação real do job (review rodada 1) | `grep -n "job_action" backend/src/notisbook/api/spark.py frontend/src/components/spark/usePackages.ts` ≥ 2 | bugfix |
| T8 | Config só bloqueado por job de install, não de libs (review rodada 1) | `grep -n 'kind === "install"' frontend/src/components/spark/InstalledList.tsx` ≥ 1 | bugfix |
| T7 | Ação de adicionar registrada como "add" no job de libs (review rodada 2) | `grep -n 'version, "add",' backend/src/notisbook/api/spark.py` ≥ 1; `grep -c 'version, "install",' backend/src/notisbook/api/spark.py` = 0 | bugfix |
| T4 | Libs core fora da lista e recusadas em add/upgrade/uninstall (teste do operador) | `grep -n "is protected" backend/src/notisbook/api/spark.py` ≥ 1; `grep -n "core_names" backend/src/notisbook/api/spark.py` ≥ 1 | bugfix |
| T4 | Toda instalação fixa as libs core na versão atual (teste do operador) | `grep -n "def core_pins" backend/src/notisbook/spark/packages.py` ≥ 1; `grep -n "core_pins(" backend/src/notisbook/api/spark.py backend/src/notisbook/spark/installer.py` ≥ 1 | bugfix |
| T7 | Selo core removido da lista (teste do operador) | `grep -c ">core<" frontend/src/components/spark/PackagesDialog.tsx` = 0 | bugfix |
| T7 | Fechar o modal Add não fecha o Config (teste do operador) | `grep -c "e.target !== e.currentTarget" frontend/src/components/spark/PackagesDialog.tsx` ≥ 2 | bugfix |
| T7 | Lista do Config e campos do Add na fonte da interface (sans), não mono; log do uv segue mono (teste do operador) | `grep -c "styles.mono" frontend/src/components/spark/PackagesDialog.tsx` = 0; `grep -c "font-mono" frontend/src/components/spark/Spark.module.css` = 4 (só as regras pré-existentes) | bugfix |

## Arquivos previstos
- `backend/pyproject.toml` — T1
- `backend/uv.lock` — T1
- `backend/src/notisbook/spark/requirements.py` — T1
- `backend/src/notisbook/spark/installer.py` — T2, T3
- `backend/src/notisbook/api/spark.py` — T2, T3, T4
- `backend/src/notisbook/spark/kernelspec.py` — T3
- `backend/src/notisbook/app.py` — T3, T4
- `backend/src/notisbook/spark/packages.py` — T4
- `backend/src/notisbook/api/sessions.py` — T5
- `frontend/src/api/types.ts` — T6
- `frontend/src/api/spark.ts` — T6
- `frontend/src/components/spark/useSparkData.ts` — T6
- `frontend/src/components/spark/PackagesDialog.tsx` — T7
- `frontend/src/components/spark/AddLibraryDialog.tsx` — T7
- `frontend/src/components/spark/usePackages.ts` — T7
- `frontend/src/components/spark/JobProgress.tsx` — T7
- `frontend/src/components/spark/Spark.module.css` — T7, T8
- `frontend/src/components/spark/InstalledList.tsx` — T8
- `frontend/src/components/spark/SparkSettings.tsx` — T8

## Fora de escopo
- Validação de requisitos de sistema no `start.sh` — adiada pelo operador.
- Validação de compatibilidade entre libs/ambiente — próximo plano.
- Detectar dependência transitiva que troca lib `core`; remover dependências órfãs no uninstall.
- Testes automatizados — não pedidos; repo não tem suíte.
- **Documentação de produto** — nenhuma. Reportada ao operador no fim, não corrigida aqui.

## Não mexer
- Mecanismo global de pré-requisitos (`api/system.py`, `PrereqsPanel`).
- Matriz do bundle e pinagens de instalação do Spark (`spark/bundles.py`, comando de install em `installer.py`).
- `warehouse/`, `metastore/` e `duckdb/extensions` sob o home do Notisbook.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6  - [x] T7  - [x] T8

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 102469 | 70131 |
| 0 | software-architect | OK | 225064 | 72664 |
| 1 | python-engineer | OK | 312667 | 128253 |
| 1 | code-review | OK | 211625 | 98430 |
| 1 | plan-auditor | OK | 32665 | 32055 |
| 2 | python-engineer | OK | 49487 | 44328 |
| 2 | code-review | OK | 61352 | 89897 |
| 2 | plan-auditor | OK | 33234 | 28847 |
| 3 | python-engineer | OK | 8642 | 25683 |
| 3 | code-review | OK | 39243 | 85593 |
| 3 | plan-auditor | OK | 29230 | 31102 |
| 4 | bug-engineer | OK | 42652 | 27432 |
| 4 | python-engineer | OK | 49488 | 42004 |
| 4 | python-engineer | OK | 20557 | 28002 |
| 4 | code-review | OK | 123330 | 82216 |
| 4 | plan-auditor | OK | 37027 | 34032 |
| 5 | memory-manager | OK | 19955 | 50389 |
<!-- effort-ledger:end -->
