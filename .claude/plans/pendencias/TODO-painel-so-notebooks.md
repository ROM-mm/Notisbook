# Pendências cosméticas — painel só com notebooks e artefatos Spark

Branch: main   Fluxo: CODE-CHANGE   Peso: expresso

## Objetivo

Nits do code review do plano `painel-so-notebooks`, fora do gatilho do loop.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `backend/src/notisbook/spark/installer.py:246-249` — escrita de `spark-defaults.conf` duplicada nos dois ramos; extrair helper `_write_defaults` (mantendo a escrita após o download no ramo com bundle) | python-engineer | — | 1 | escrita |
| T2 | `backend/src/notisbook/spark/installer.py:244` — ambientes sem bundle já instalados ficam sem `spark-defaults.conf` e não são marcados `outdated`; avisar na mensagem do instalador/UI que precisam ser reinstalados | python-engineer | — | 1 | escrita |
| T3 | `frontend/src/components/files/FileBrowser.tsx:40` — `EntryIcon` aceita `file` e mostra ícone de notebook; restringir o prop a `"dir" \| "notebook"` com type guard no filtro | python-engineer | — | 1 | escrita |
| T5 | `frontend/src/components/files/FileBrowser.tsx:196` — pasta só com arquivos escondidos mostra "Empty folder"; usar "No notebooks here…" quando `entries.length > 0` e `visibleEntries.length === 0` | python-engineer | — | 1 | escrita |
| T4 | CSS `.iconFile`/`.nameText` em `FileBrowser.module.css` e export `FileIcon` em `shell/icons.tsx` ficaram sem uso | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Uma única rotina escreve `spark-defaults.conf` | `grep -c 'spark-defaults.conf' backend/src/notisbook/spark/installer.py` → 1 escrita | refactor |
| T2 | Ambiente sem bundle antigo é sinalizado para reinstalação | leitura do código de status do ambiente/instalador | feature |
| T3 | `EntryIcon` não aceita `file` | `grep -n 'Exclude<ContentEntry\["type"\], "file">' frontend/src/components/files/FileBrowser.tsx` → presente | refactor |
| T5 | Mensagem distingue pasta vazia de pasta sem notebooks | leitura de `FileBrowser.tsx`: dois textos, condicionados a `entries.length` | feature |
| T4 | Sem CSS/export morto | `git grep -n 'iconFile\|nameText\|FileIcon' -- frontend/src` → nenhuma ocorrência | refactor |

## Arquivos previstos
- `backend/src/notisbook/spark/installer.py` — T1, T2
- `frontend/src/components/files/FileBrowser.tsx` — T3
- `frontend/src/components/files/FileBrowser.module.css` — T4
- `frontend/src/components/shell/icons.tsx` — T4

## Fora de escopo
- **Documentação de produto** — nenhuma.

## Não mexer
- Conteúdo gerado do `spark-defaults.conf`.

## Status
- [ ] T1  - [ ] T2  - [ ] T3  - [ ] T4  - [ ] T5

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
<!-- effort-ledger:end -->

## Fechados em 2026-11-10 (commit 1c66b56, plano correcoes-pendencias-alta)
- T3 obsoleto (FileBrowser refeito como árvore); T4 parcial: FileIcon em uso, CSS segue morto
