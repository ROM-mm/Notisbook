# Publicar release 0.1.0 e tap Homebrew

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-11 11:48:28 -0300
Modificação: 2026-11-11 13:05:27 -0300
Finalização: 2026-11-11 13:05:27 -0300

## Objetivo

Chegar a `brew install rom-mm/tap/notisbook` funcionando a partir do GitHub: código em `ROM-mm/Notisbook`, release `v0.1.0` com o sdist (frontend embutido) e a fórmula num tap novo `ROM-mm/homebrew-tap`. A ordem corrige o risco achado na análise do `brew.md`: árvore limpa → tag → build → upload → sha256 do asset baixado (o build roda depois da tag, sobre o commit da tag). Push e operações no GitHub (release, criação de repo) só por ação ou autorização explícita do operador por comando.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Commitar o pendente (planos + `.gitignore`) e deixar a árvore limpa | tech-lead (git-workflow) | — | 1 | escrita |
| T2 | `git push origin main` | **operador** | T1 | 2 | escrita |
| T3 | Tag `v0.1.0` no HEAD publicado e build com `scripts/build_release.py` | tech-lead | T2 | 3 | escrita |
| T4 | `git push origin v0.1.0` + `gh release create` com o sdist | **operador** (release: tech-lead com autorização) | T3 | 4 | escrita |
| T5 | Criar o tap local (`brew tap-new rom-mm/tap`) e o repo remoto (`gh repo create … --push`) | tech-lead local; remoto **operador** | T4 | 5 | escrita |
| T6 | Escrever `Formula/notisbook.rb`, gerar `resource` e validar com install/test/audit | python-engineer | T5 | 6 | escrita |
| T7 | Commit da fórmula no tap; push pelo **operador**; install final a partir do remoto | tech-lead + **operador** | T6 | 7 | escrita |

## Ordem de execução (waves)
- Serial, uma wave por vez, cada push/operação remota parando para o operador: T1 → T2 → T3 → T4 → T5 → T6 → T7

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Build depois da tag, sobre árvore limpa | garante que o sdist corresponde ao commit da tag | `scripts/build_release.py` não checa árvore limpa nem tag (análise knowledge-engineer) | build antes da tag, como no `brew.md` §1-2 — descartado |
| D2 | `sha256` da fórmula calculado sobre o asset baixado da release | rebuild muda o hash (mtimes no tar) | análise knowledge-engineer | hash impresso pelo script — só conferência |
| D3 | Fórmula com `depends_on "uv"` além de python@3.12, openjdk@17 e rust (build) | instalar Spark aborta sem uv | `backend/src/notisbook/spark/installer.py:404-406` | uv como pré-requisito manual — descartado |
| D3a | Deps extras `zeromq`, `pkgconf` (build) e `libyaml` | 1º install falhou no build do pyzmq (libzmq não achado); audit exigiu libyaml para pyyaml | `Formula/notisbook.rb:10,12,16`; log Homebrew `30.python3.12.log` | sem elas — install/audit falham |
| D3b | `brew trust --formula rom-mm/tap/notisbook` na config do Homebrew do operador (fora do write_scope) | o Homebrew recusa carregar fórmula de tap não confiável | retorno do python-engineer | trust do tap inteiro — mais amplo, descartado |
| D4 | Fórmula delegada ao python-engineer | é empacotamento de app Python (virtualenv + resources); memória do projeto atribui toda implementação a ele | memória `python-engineer-implementa-back-e-front` | swift-engineer (cobre Homebrew, mas não Python) |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Árvore limpa no Notisbook-app | `git status --porcelain` → vazio | constraint |
| T2 | `main` local igual ao remoto | `git rev-parse main` == `git rev-parse origin/main` (após `git fetch`) | constraint |
| T3 | Tag aponta para o HEAD publicado e bate com a versão | `git rev-parse v0.1.0^{commit}` == `git rev-parse origin/main`; `grep '^version = "0.1.0"' backend/pyproject.toml` | constraint |
| T3 | sdist contém o frontend e nada de `.claude`/`.idea`/`.DS_Store` | `tar -tzf backend/dist/notisbook-0.1.0.tar.gz \| grep -c '_frontend/index.html'` → 1; `… \| grep -E '\.claude\|\.idea\|\.DS_Store'` → vazio | feature |
| T4 | Release pública com o asset | `gh release view v0.1.0 -R ROM-mm/Notisbook --json assets -q '.assets[].name'` → `notisbook-0.1.0.tar.gz` | feature |
| T5 | Tap remoto público existe | `gh repo view ROM-mm/homebrew-tap --json visibility -q .visibility` → `PUBLIC` | feature |
| T6 | Fórmula declara url/sha256 do asset e as dependências de D3 | `grep -E 'releases/download/v0.1.0/notisbook-0.1.0.tar.gz\|depends_on "uv"\|depends_on "openjdk@17"\|depends_on "python@3.12"' Formula/notisbook.rb` → 4 linhas; sha256 == `shasum -a 256` do asset baixado | feature |
| T6 | Instala do código-fonte e passa no teste | `brew install --build-from-source rom-mm/tap/notisbook` exit 0; `brew test rom-mm/tap/notisbook` exit 0; `notisbook --version` → `0.1.0` | feature |
| T6 | Sem erros de estilo da fórmula | `brew audit --strict rom-mm/tap/notisbook` exit 0 (achados de `--new` reportados, não bloqueiam) | constraint |
| T7 | Install funciona a partir do tap remoto | `brew uninstall notisbook && brew untap rom-mm/tap && brew install rom-mm/tap/notisbook` exit 0; `notisbook --version` → `0.1.0` | feature |

## Arquivos previstos
- `.claude/plans/INDEX.md` — T1
- `.claude/plans/completed/20261111_main_botao-run-sem-sombra.md` — T1
- `.gitignore` — T1
- `$(brew --repository rom-mm/tap)/Formula/notisbook.rb` — T6

## Fora de escopo
- Painel de pré-requisitos não achar o keg `openjdk@17` (`prereqs.py:75-85`) — mudança de código separada, plano próprio.
- Workflow de CI gerado pelo `brew tap-new` (bottles) — mantido como gerado, sem ajuste.
- `brew bump-formula-pr` e automação de versões futuras.
- **Documentação de produto** — `brew.md` fica desatualizado (ordem da release, `depends_on "uv"`, `--port`); está no `.gitignore` do operador. Reportado no fim, não corrigido aqui.

## Não mexer
- Código de `backend/` e `frontend/` (nenhum fonte da aplicação muda neste plano).
- `backend/pyproject.toml` (versão 0.1.0 permanece).
- Nenhum `git push` executado pelo tech-lead.

## Status
- [x] T1 (8fab040)  - [~] T2 (push do operador em d97106f; 8fab040 — só plano/.gitignore — ainda não publicado)  - [x] T3  - [x] T4 (release v0.1.0 → d97106f, tag criada pelo gh; sha ae368938…76f4 conferido no asset baixado)  - [x] T5 (repo local git init d6b9126; ROM-mm/homebrew-tap criado pelo tech-lead com autorização do operador; visibility=PUBLIC)  - [x] T6 (review: aprovar; auditoria: PARCIALMENTE AUDITÁVEL, criterios_falhos=[])  - [x] T7 (tap e1fd0e1 e app 58e9949 publicados pelo operador; uninstall+untap+install do remoto exit 0, --version 0.1.0, brew test exit 0)
- [x] T2 (main == origin/main == 58e9949 após o push do operador)

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 88921 | 46395 |
| 6 | python-engineer | OK | 2296182 | 66269 |
| 6 | code-review | aprovar | 58893 | 66482 |
| 6 | plan-auditor | PARCIALMENTE AUDITÁVEL | 63235 | 27331 |
<!-- effort-ledger:end -->
