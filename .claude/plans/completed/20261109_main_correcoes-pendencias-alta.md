# Correções de alta importância das pendências de review

Branch: main   Fluxo: BUG   Peso: completo

Criação:     2026-11-09 17:18:21 -0300
Modificação: 2026-11-10 02:25:31 -0300
Finalização: 2026-11-10 02:25:31 -0300

## Objetivo

Corrigir os nits de `.claude/plans/pendencias/` que a triagem de 2026-11-09 (3 knowledge-engineer, HEAD `f43299e`) confirmou como bug real ou risco de segurança no código atual. Os itens cosméticos e os opcionais ficaram fora por decisão do operador.

**Restrição do operador (inegociável): nenhuma correção pode quebrar o que funciona hoje.** Cada fix é mínimo e local ao defeito; nada de refatoração de carona; o comportamento correto existente fica idêntico. Fix que exija mudar comportamento além do defeito volta ao operador antes de ser aplicado. Linhas citadas são as do HEAD `f43299e`.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Token de sessão não aparece no access log do uvicorn (`__main__.py:56`; token vai em `?token=` — `frontend/src/api/auth.ts:15`, `security.py:63`) | python-engineer | — | 1 | escrita |
| T2 | Checagem de sessão aberta em delete/rename insensível a caixa no APFS (`service.py:636-638`, `store.py:226-228`, `api/contents.py:83,96-100`) | python-engineer | — | 1 | escrita |
| T3 | `PartialDelete` só em falha parcial real; `OSError` do `unlink` não vira 500 com caminho absoluto (`store.py:252-253`) | python-engineer | — | 1 | escrita |
| T4 | Export `.py` não reescreve linhas `%`/`!` dentro de string tripla (`export/py_source.py:29-36`) | python-engineer | — | 1 | escrita |
| T5 | Regra única de "env gerenciado" usada por `_ensure_log4j2` e `kernelspec._entry` (`service.py:582-589`, `kernelspec.py:143`) | python-engineer | — | 1 | escrita |
| T6 | Smoke da JVM com timeout; travamento libera o lock e falha o job (`installer.py:482`) | python-engineer | — | 1 | escrita |
| T7 | `_cleanup` com sessão ativa remove órfãos e preserva só envs em uso; warning diz quando sai (`installer.py:491-499`) | python-engineer | — | 1 | escrita |
| T8 | `IncompleteRead`/`HTTPException` no download viram erro "cannot download <jar>" (`installer.py:431-434`) | python-engineer | — | 1 | escrita |
| T9 | add/upgrade de pacotes checa sessão/lock antes de `_pins` → 409; `_pins` sem busca duplicada e docstring fiel; mensagem do 409 de remove correta (`api/spark.py:183,197,216-222,241-262`) | python-engineer | — | 1 | escrita |
| T10 | `resolve_java_home` usa `_java_home_tool()` (`spark/prereqs.py:80-81`) | python-engineer | — | 1 | escrita |
| T11 | WS de job detecta desconexão do cliente sem esperar evento (`api/jobs.py:45-46`, `jobs.py:81`) | python-engineer | — | 1 | escrita |
| T12 | Nome de pasta com espaço final preservado (`files/native_picker.py:100`) | python-engineer | — | 1 | escrita |
| T13 | `_mro` não passa pela metaclasse (`kernels/introspect.py:251`) | python-engineer | — | 1 | escrita |
| T14 | Cancel no `DirectoryPicker` aborta a validação e não chama `onSelect` (`data/DirectoryPicker.tsx:28-29`) | python-engineer | — | 2 | escrita |
| T15 | Nó de variável com primeiro fetch cancelado é refeito no `toggle` (`state/variables.ts:180,188,249`) | python-engineer | — | 2 | escrita |
| T16 | Falha transitória de revalidação mantém `entries`; docstrings de `notebookTree.ts:52,61` fiéis (`state/notebookTree.ts:93,105`) | python-engineer | — | 2 | escrita |
| T17 | Esc limpa a seleção só com foco na árvore (`files/FileBrowser.tsx:44-52`) | python-engineer | — | 2 | escrita |
| T18 | `revokeObjectURL` adiado o suficiente para o download iniciar (`lib/download.ts:11`) | python-engineer | — | 2 | escrita |
| T20 | `rootCause` é a causa mais interna, não o topo (`outputs/sparkError.ts:99`) | python-engineer | — | 2 | escrita |
| T21 | Seletor do campo de caminho casa com o input (`data/DataPanel.module.css:104`) | python-engineer | — | 2 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita, backend): T1–T13
- Wave 2 (serial, escrita, frontend): T14–T21

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Entram só bug real/segurança | operador pediu "os mais importantes num só plano" | triagem de 2026-11-09 nesta sessão | incluir todos os ~130 válidos (descartado: plano inauditável) |
| D3 | T19 retirado do plano | frontend não distingue kernel com SQL (todo kernel é Spark, `language` sempre python); esconder arriscaria opção válida | retorno do python-engineer wave 2; auditoria rodada 1 | adicionar campo no backend (descartado: muda contrato) |
| D4 | Gate do backend = compileall | repo sem testes versionados; pytest sai 5 sem referente | `pytest` exit 5 "no tests ran" | manter pytest (inauditável) |
| D5 | 409 de install também com texto "Another job for Spark X is in progress" | lock é compartilhado; texto antigo era impreciso | `api/spark.py:183`; aceite do operador 2026-11-09 | manter texto antigo |
| D2 | Frontend também com `python-engineer` | precedente dos planos anteriores deste repo; não há engineer de TS/React | `.claude/plans/completed/*` (169 linhas python-engineer) | — |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Access log sem token | leitura de `backend/src/notisbook/__main__.py:main` — `access_log=False` ou filtro que remove `token=` | bugfix |
| T2 | `A.ipynb` bloqueado com sessão em `a.ipynb` | `grep -n "casefold\|lower()\|samefile\|normcase" backend/src/notisbook/kernels/service.py` dentro de `has_session_under` | bugfix |
| T3 | `unlink` falho não vira `PartialDelete` nem ecoa caminho absoluto | leitura de `backend/src/notisbook/notebooks/store.py` no ramo de delete | bugfix |
| T4 | Linhas dentro de `"""…"""` passam intactas | leitura de `backend/src/notisbook/export/py_source.py:_python_block` — rastreia estado de string tripla | bugfix |
| T5 | Um helper só decide "env gerenciado" | `grep -rn "def .*managed" backend/src/notisbook/spark/kernelspec.py` e uso em `kernels/service.py:_ensure_log4j2` | bugfix |
| T6 | Smoke com timeout | `grep -n "timeout" backend/src/notisbook/spark/installer.py` na chamada do smoke | bugfix |
| T7 | Cleanup não sai cedo com sessão ativa | leitura de `backend/src/notisbook/spark/installer.py:_cleanup` | bugfix |
| T8 | Download truncado gera erro nomeando o jar | `grep -n "IncompleteRead\|HTTPException" backend/src/notisbook/spark/installer.py` | bugfix |
| T9 | Checagem 409 antes de `_pins` | leitura de `backend/src/notisbook/api/spark.py:add_packages`/`upgrade_packages` | bugfix |
| T9 | 409 de remove não diz "Install" | `grep -n "Install .* in progress" backend/src/notisbook/api/spark.py` sem ocorrência no handler de remove | bugfix |
| T10 | Override respeitado | `grep -n "_java_home_tool()" backend/src/notisbook/spark/prereqs.py` em `resolve_java_home` | bugfix |
| T11 | Desconexão detectada durante espera | leitura de `backend/src/notisbook/api/jobs.py` — espera concorrente com recepção do socket | bugfix |
| T12 | Sem `strip()` que corte espaço do nome | leitura de `backend/src/notisbook/files/native_picker.py:100` | bugfix |
| T13 | MRO sem passar pela metaclasse | leitura de `backend/src/notisbook/kernels/introspect.py:_mro` | bugfix |
| T1–T13 | Backend compila | `cd backend && uv run python -m compileall -q src` sai 0 | constraint |
| T14 | Cancel não altera raiz | `grep -n "AbortController\|signal" frontend/src/components/data/DirectoryPicker.tsx` | bugfix |
| T15 | `toggle` refaz fetch de nó sem itens carregados | leitura de `frontend/src/state/variables.ts:toggle` | bugfix |
| T16 | `entries` preservado em falha | leitura de `frontend/src/state/notebookTree.ts` no `catch` da revalidação | bugfix |
| T17 | Esc condicionado ao foco na árvore | leitura de `frontend/src/components/files/FileBrowser.tsx` no handler de `keydown` | bugfix |
| T18 | Revoke adiado | `grep -n "revokeObjectURL" frontend/src/lib/download.ts` com atraso > 0 | bugfix |
| T20 | `rootCause` = última causa | leitura de `frontend/src/components/outputs/sparkError.ts:99` | bugfix |
| T21 | Seletor sem classe de módulo inexistente | leitura de `frontend/src/components/data/DataPanel.module.css:104` | bugfix |
| T14–T21 | Typecheck e build do frontend passam | `cd frontend && npm run build` sai 0 | constraint |

## Arquivos previstos
- `backend/src/notisbook/__main__.py` — T1
- `backend/src/notisbook/kernels/service.py` — T2, T5
- `backend/src/notisbook/notebooks/store.py` — T2, T3
- `backend/src/notisbook/api/contents.py` — T2
- `backend/src/notisbook/export/py_source.py` — T4
- `backend/src/notisbook/spark/kernelspec.py` — T5
- `backend/src/notisbook/spark/installer.py` — T6, T7, T8
- `backend/src/notisbook/api/spark.py` — T9
- `backend/src/notisbook/spark/prereqs.py` — T10
- `backend/src/notisbook/api/jobs.py` — T11
- `backend/src/notisbook/jobs.py` — T11
- `backend/src/notisbook/files/native_picker.py` — T12
- `backend/src/notisbook/kernels/introspect.py` — T13
- `frontend/src/components/data/DirectoryPicker.tsx` — T14
- `frontend/src/state/variables.ts` — T15
- `frontend/src/state/notebookTree.ts` — T16
- `frontend/src/components/files/FileBrowser.tsx` — T17
- `frontend/src/lib/download.ts` — T18
- `frontend/src/components/outputs/sparkError.ts` — T20
- `frontend/src/components/data/DataPanel.module.css` — T21
- `.claude/plans/pendencias/*.md` — fechamento dos itens atendidos/obsoletos (tech-lead)

## Fora de escopo
- Nits cosméticos (idioma, comentários, formatação) — baixa importância.
- Opcionais: CSP de estáticos, stderr do `uv pip list`, contagem do export, paginação "Carregar mais", painel de variáveis (páginas/visibilidade/poda/rótulos), env Spark sem `spark-defaults`, boot com `/api/notebooks-root`, código morto.
- T19 (seletor SQL só com kernel compatível) — retirado por decisão do operador (D3); volta às pendências.
- Convenção de idioma de docstrings — aguarda decisão do operador.
- Criação de testes novos — não pedida.
- **Documentação de produto** — nenhuma.

## Não mexer
- Comportamento hoje correto de qualquer arquivo tocado — mudança só no caminho do defeito de cada Tn.
- Testes existentes — nenhum removido, pulado ou com expectativa alterada.
- Contrato público das rotas (paths, payloads) além dos status/textos corrigidos em T3/T9 (D5).
- `_ALLOWED_CLASSES` e `_SANITIZE` de `backend/src/notisbook/export/html_report.py`.

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6  - [x] T7  - [x] T8  - [x] T9  - [x] T10  - [x] T11  - [x] T12  - [x] T13
- [x] T14  - [x] T15  - [x] T16  - [x] T17  - [x] T18  - [x] T20 (já satisfeito no baseline, sem mudança)  - [x] T21

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer (triagem backend) | OK | 214245 | 112202 |
| 0 | knowledge-engineer (triagem painéis) | OK | 231627 | 103470 |
| 0 | knowledge-engineer (triagem UI) | OK | 106484 | 58293 |
| 1 | python-engineer | OK | 146386 | 76849 |
| 2 | python-engineer | OK | 74204 | 52851 |
| 3 | code-review | OK | 136698 | 88301 |
| 3 | plan-auditor | OK | 87181 | 46796 |
| 3 | plan-auditor (rodada 2) | OK | 54138 | 39440 |
<!-- effort-ledger:end -->
