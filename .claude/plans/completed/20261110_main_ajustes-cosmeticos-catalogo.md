# Ajustes cosméticos do catálogo e dos menus

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 19:14:32 -0300
Modificação: 2026-11-10 19:35:59 -0300
Finalização: 2026-11-10 19:35:59 -0300

## Objetivo

Aplicar os nits registrados pelo code review nos planos `catalogo-sqlite-persistente` e `menus-schema-e-pasta` (pendências `.claude/plans/pendencias/TODO-catalogo-sqlite-persistente.md` e `TODO-menus-schema-e-pasta.md`, consolidadas aqui a pedido do operador). Sem mudança de comportamento além do que cada item descreve.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `kernels/catalog_hook.py` — fallback de rename por formato+schema só quando a célula casa `RENAME` (DROP a + CREATE b não vira rename) | python-engineer | — | 1 | escrita |
| T2 | `api/catalog.py` — `Kernels`/`get_kernels` saem do router do catálogo para um módulo de dependências comum; `api/variables.py` deixa de importar de `api/catalog.py` | python-engineer | — | 1 | escrita |
| T3 | `kernels/catalog_hook.py` — comentários em pt-BR no template do kernel (resto em inglês) uniformizados | python-engineer | — | 1 | escrita |
| T4 | `catalog/schemas.py` — DELETE de schema sem `catalog.db` responde 404 sem criar o arquivo | python-engineer | — | 1 | escrita |
| T5 | `catalog/iceberg_jdbc.py` — prefixo de namespace comparado respeitando caixa (LIKE do SQLite ignora caixa ASCII) | python-engineer | — | 1 | escrita |
| T6 | `files/browser.py` — symlink quebrado pode ser removido (hoje `not_a_directory`) | python-engineer | — | 1 | escrita |
| T7 | `FileTree.tsx` — erro de Delete Folder aparece no ConfirmDialog (não fecha o diálogo) | python-engineer | — | 1 | escrita |
| T8 | `api/catalog.py` — reserva de kernels mantida até o fim da exclusão mesmo se o handler for cancelado (`asyncio.shield`) ou janela documentada | python-engineer | T2 | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2, T3, T4, T5, T6, T7, T8

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Rename só com `RENAME` na célula | `grep -n "RENAME" backend/src/notisbook/kernels/catalog_hook.py` mostra a condição no fallback de `match_renames` | refactor |
| T2 | Variables não importa de `api/catalog.py` | `grep -n "from .catalog import\|from notisbook.api.catalog import" backend/src/notisbook/api/variables.py` vazio | refactor |
| T3 | Template do kernel num idioma só | `grep -nE "^\s*#.*(ç|ã|õ|é)" backend/src/notisbook/kernels/catalog_hook.py` restrito ao template não acha comentários em pt-BR | refactor |
| T4 | DELETE sem catalog.db → 404 sem criar o arquivo | curl DELETE com home vazio → 404 `schema_not_found` e `test -f <home>/catalog.db` falso | bugfix |
| T5 | Prefixo de namespace com caixa | `grep -n "substr\|case_sensitive_like" backend/src/notisbook/catalog/iceberg_jdbc.py` | bugfix |
| T6 | Symlink quebrado removível | curl `DELETE /api/fs/dir` em link pendente sob $HOME → 204 e o link some | bugfix |
| T7 | Erro de exclusão no diálogo | `grep -n "error=" frontend/src/components/data/FileTree.tsx` no ConfirmDialog | refactor |
| T8 | Reserva sobrevive a cancelamento | `grep -n "shield" backend/src/notisbook/api/catalog.py` ou docstring de `reserve_idle` citando a janela | refactor |
| T1 | Gates | `python -m compileall backend/src` e `cd frontend && npm run typecheck` exit 0; `run_all.sh` e `m5/verify.sh` (regressão) exit 0 | constraint |

## Arquivos previstos
- `backend/src/notisbook/kernels/catalog_hook.py` — T1, T3
- `backend/src/notisbook/api/catalog.py` — T2, T8
- `backend/src/notisbook/api/variables.py` — T2
- `backend/src/notisbook/api/deps.py` — T2
- `backend/src/notisbook/catalog/schemas.py` — T4
- `backend/src/notisbook/catalog/iceberg_jdbc.py` — T5
- `backend/src/notisbook/files/browser.py` — T6
- `backend/src/notisbook/kernels/service.py` — T8
- `frontend/src/components/data/FileTree.tsx` — T7
- `.claude/plans/pendencias/TODO-catalogo-sqlite-persistente.md` — consolidado aqui (removido)
- `.claude/plans/pendencias/TODO-menus-schema-e-pasta.md` — consolidado aqui (removido)

## Fora de escopo
- Qualquer mudança de comportamento além dos oito itens; testes automatizados.
- **Documentação de produto** — nenhuma.

## Não mexer
- Sonda do painel Variables (comportamento); política de allowlist do Delete Folder; contrato REST existente (só T4 muda o caso sem catalog.db).

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6  - [x] T7  - [x] T8

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 633784 | 77723 |
| 2 | code-review (skill) | aprovar | 73228 | 71439 |
| 2 | plan-auditor | OK | 32614 | 28183 |
<!-- effort-ledger:end -->
