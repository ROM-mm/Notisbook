# Pendências cosméticas — Painel Dados funcional

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

Criação:     2026-11-05 11:56:11 -0300
Modificação: 2026-11-05 12:37:41 -0300
Finalização: —

## Objetivo

Achados `nit` do code review do plano `20261105_main_painel-dados-funcional` (rodadas 1, 3, 5, 6, 7 e 8), fora do gatilho do loop. Retomada a critério do operador.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| N1 | `backend/src/notisbook/files/browser.py:62`: docstring diz "no symlink traversal", mas link de diretório segue navegável | python-engineer | — | 1 | escrita |
| N2 | `backend/src/notisbook/api/catalog.py:25`: parâmetro `op: Any` deveria ser `Op` | python-engineer | — | 1 | escrita |
| N3 | (obsoleto em parte — seletor in-app removido; vale para o campo de colar caminho) `frontend/src/components/data/DirectoryPicker.tsx`: caminho digitado não é normalizado (`..`, `//`, barra final) | python-engineer | — | 1 | escrita |
| N4 | `frontend/src/state/files.ts:127`: `refresh` recarrega expandidos sob pais recolhidos | python-engineer | — | 1 | escrita |
| N5 | `backend/src/notisbook/kernels/introspect.py:88-91`: tabela `limit+2` lida via Py4J e descartada | python-engineer | — | 1 | escrita |
| N6 | ~~`DirectoryPicker.tsx`: erro do campo/paginação desabilita "Usar esta pasta"~~ obsoleto — botão removido na D1 revisada | python-engineer | — | 1 | escrita |
| N7 | `backend/src/notisbook/api/catalog.py:56`: 409 com status cru exibido na UI de colunas | python-engineer | — | 1 | escrita |
| N8 | `frontend/src/state/files.ts:77-84`: falha de paginação some com "Carregar mais" | python-engineer | — | 1 | escrita |
| N9 | `backend/src/notisbook/kernels/introspect.py:134`: comentário em português no meio de `_KERNEL_SOURCE` em inglês | python-engineer | — | 1 | escrita |
| N10 | `frontend/src/components/data/FilesSection.tsx:24`: sucesso do Finder não limpa `manual`/`notice` | python-engineer | — | 1 | escrita |
| N11 | `frontend/src/components/data/DirectoryPicker.tsx:28`: validação sem `AbortSignal` troca a raiz após "Cancelar" | python-engineer | — | 1 | escrita |
| N12 | `backend/src/notisbook/files/native_picker.py:91`: `strip()` corta espaço final do nome da pasta | python-engineer | — | 1 | escrita |
| N13 | `frontend/src/api/files.ts:3,27-28`: `FsPlace`/`getPlaces` sem uso no frontend | python-engineer | — | 1 | escrita |
| N14 | `frontend/src/components/data/DataPanel.module.css:100`: `.pathForm .input` não pega o `input` global do campo | python-engineer | — | 1 | escrita |
| N15 | `frontend/src/components/data/FilesSection.tsx:35`: mensagem genérica emendada sem pontuação | python-engineer | — | 1 | escrita |
| N16 | `frontend/src/components/data/CatalogSection.tsx:350`: linha só para o botão de atualizar gasta altura; levar para a linha do título | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): N1 → N2 → N3 → N4 → N5 → N6 → N7 → N8 → N9 → N10 → N11 → N12 → N13 → N14 → N15 → N16

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| N1 | Docstring fiel ao comportamento | `grep -n "no symlink traversal" backend/src/notisbook/files/browser.py` → vazio | refactor |
| N2 | `op` tipado | `grep -n "op: Any" backend/src/notisbook/api/catalog.py` → vazio | refactor |
| N3 | Caminho normalizado | `/api/fs/list?path=/usr//bin/` → `jq -r .path` = `/usr/bin` | feature |
| N5 | Corte imediato no limite | `introspect.py`: `break` logo após o append quando `len(tables) > limit` (leitura do código) | refactor |
| N6 | Botão só bloqueado por erro de listagem | `DirectoryPicker.tsx`: erro de campo/paginação separado do erro de listagem (leitura do código) | refactor |
| N7 | Status traduzido | `frontend/src/state/catalog.ts` mapeia `busy`/`no_spark_session`/`kernel_dead` para pt-BR (leitura do código) | refactor |
| N8 | Retentar paginação | `frontend/src/state/files.ts`: erro com `offset > 0` preserva `nextOffset` (leitura do código) | refactor |
| N9 | Comentário em inglês | `grep -n "Só global temp views" backend/src/notisbook/kernels/introspect.py` → vazio | refactor |
| N10 | Estado limpo após sucesso | `FilesSection.tsx`: `setManual(false)`/`setNotice(null)` no sucesso (leitura do código) | refactor |
| N11 | Validação cancelável | `grep -n "AbortController" frontend/src/components/data/DirectoryPicker.tsx` → ≥ 1 linha | refactor |
| N12 | Caminho preserva espaço final | `grep -n 'rstrip("\\n")' backend/src/notisbook/files/native_picker.py` → ≥ 1 linha | refactor |
| N13 | Sem cliente morto | `getPlaces` removido de `frontend/src/api/files.ts` ou comentado como mantido de propósito (leitura do código) | refactor |
| N14 | Campo ocupa a largura | `grep -nE ":global\\(.input\\)\|pathInput" frontend/src/components/data/DataPanel.module.css` → ≥ 1 linha | refactor |
| N15 | Mensagem pontuada | `FilesSection.tsx`: separador ou ponto final entre `errorMessage(err)` e a orientação (leitura do código) | refactor |
| N16 | Ações na linha do título | `CatalogSection.tsx`: botão e selo no mesmo contêiner flex do `<h3>` (leitura do código) | refactor |
| N4 | Refresh só do visível | `refresh` em `frontend/src/state/files.ts` percorre a partir da raiz só nós com pai expandido (leitura do código) | refactor |

## Arquivos previstos
- `backend/src/notisbook/files/browser.py` — N1, N3
- `backend/src/notisbook/api/catalog.py` — N2
- `frontend/src/components/data/DirectoryPicker.tsx` — N3
- `frontend/src/state/files.ts` — N4, N8
- `backend/src/notisbook/kernels/introspect.py` — N5, N9
- `frontend/src/components/data/DirectoryPicker.tsx` — N6
- `backend/src/notisbook/api/catalog.py` — N7
- `frontend/src/state/catalog.ts` — N7
- `frontend/src/components/data/FilesSection.tsx` — N10
- `frontend/src/components/data/DirectoryPicker.tsx` — N11
- `backend/src/notisbook/files/native_picker.py` — N12
- `frontend/src/api/files.ts` — N13
- `frontend/src/components/data/DataPanel.module.css` — N14
- `frontend/src/components/data/FilesSection.tsx` — N15
- `frontend/src/components/data/CatalogSection.tsx` — N16

## Fora de escopo
- Qualquer mudança de comportamento além do apontado em cada nit.
- **Documentação de produto** — nenhuma.

## Não mexer
- Contratos REST do plano principal (`/api/fs/*`, `/api/sessions/{id}/catalog*`).

## Status
- [ ] N1  - [ ] N2  - [ ] N3  - [ ] N4  - [x] N5 (feito na rodada 3 do plano principal)  - [x] N6 (obsoleto)  - [ ] N7  - [ ] N8  - [ ] N9  - [ ] N10  - [ ] N11  - [ ] N12  - [ ] N13  - [ ] N14  - [ ] N15  - [ ] N16

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- N5, N6, N16 já resolvidos ou obsoletos
- N11 resolvido (Cancel aborta validação)
- N12 resolvido (espaço final preservado)
- N14 resolvido (.pathForm input)
