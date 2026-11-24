---
description: Conduz a release do Notisbook de ponta a ponta — documentação, PR para a develop, PR para a main, CHANGELOG, testes e release manuais do operador e sincronização da develop
allowed-tools: Read, Edit, Skill(document), Bash(git status:*), Bash(git branch --show-current:*), Bash(git rev-parse:*), Bash(git fetch:*), Bash(git log:*), Bash(git diff:*), Bash(git describe:*), Bash(git add:*), Bash(git commit:*), Bash(git checkout develop:*), Bash(git checkout main:*), Bash(git pull --ff-only:*), Bash(gh auth status:*), Bash(gh pr list:*), Bash(gh pr create:*), Bash(gh pr view:*), Bash(gh release view:*), Bash(gh release list:*), Bash(date:*), Bash(grep:*)
---

# /release — release do Notisbook de ponta a ponta

## Pré-requisitos

- Rodar na raiz do repositório `Notisbook-app`, **na branch de trabalho** (feature/fix), nunca em `main` ou `develop`.
- `git` e `gh` autenticado (`gh auth status`). Para os passos manuais do operador: `uv`, `npm`, `python3`, `shasum` e Docker com o daemon ativo.
- A branch de trabalho já enviada para `origin` (`git push -u origin <branch>`) e sincronizada.
- Fluxo: branch de trabalho → PR para `develop` → PR `develop` → `main` → release a partir de `main` → PR `main` → `develop`.

## Regras gerais

- Responda em português; o texto do CHANGELOG é em **inglês**.
- Este comando **nunca** faz `git push`, **nunca** faz merge de PR, **nunca** roda `./scripts/release.sh` e **nunca** apaga arquivos. Push, merge, testes locais e release são do operador.
- Nunca use `--force`, `reset --hard`, `--no-verify`, `git add -A`/`git add .`, nem apague tags, commits ou releases.
- Pare na **primeira falha** de qualquer passo: mostre o erro (as últimas linhas relevantes) e não tente contornar.
- Cada pergunta vai **sozinha** na mensagem. Só `sim` (ou variação clara: "s", "pode", "yes") autoriza; qualquer outra resposta encerra o comando sem fazer o passo.
- "Merge feito" nunca vale sozinho: confirme sempre com `gh pr view <número> --repo ROM-mm/Notisbook --json state --jq .state` == `MERGED`. Se não for, diga o estado atual e **pare**.
- Antes de criar um PR, procure um aberto para o mesmo par head/base (`gh pr list --repo ROM-mm/Notisbook --head <head> --base <base> --state open --json number,url,title`). Se existir, reutilize-o e mostre a URL; não crie outro.
- Se a sessão cair, o operador reinicia `/release` do zero; os PRs já abertos são reutilizados pela regra acima.

## Passo 0 — checagens

```bash
git branch --show-current
git status --porcelain
gh auth status
git fetch origin
git rev-parse HEAD
git rev-parse --verify origin/<branch>
```

- Branch `main` ou `develop`: **pare** e explique que a release começa na branch de trabalho, antes do PR para a `develop`.
- `git status --porcelain` não vazio: **pare** e mostre os arquivos.
- `gh` não autenticado: **pare** (`gh auth login`).
- `origin/<branch>` inexistente ou diferente de `HEAD`: **pare** e peça ao operador para rodar `git push -u origin <branch>`.

## Passo 1 — documentação (antes do PR para a develop)

1. Pergunte, sozinho na mensagem: **"Atualizo a documentação do projeto?"** Sem `sim`, siga para o Passo 2.
2. Com `sim`, invoque a skill `document` com o alvo `projeto` e a instrução **"Atualizar toda a documentação com base no estado atual da aplicação/projeto"**. É esperado que ela reescreva `README.md`, `ARCHITECTURE.md` e `docs/` por inteiro.
3. Mostre os arquivos alterados (`git status --porcelain`). Se aparecer qualquer arquivo fora de `README.md`, `ARCHITECTURE.md` e `docs/`, **pare** e mostre-o. Sem alterações, siga para o Passo 2.
4. Commit só dos caminhos de documentação, explícitos:
   ```bash
   git add -- README.md ARCHITECTURE.md docs/
   git commit -m "docs: atualiza a documentação do projeto"
   ```
5. Peça ao operador para rodar `git push origin <branch>` e responder quando terminar. Confira com `git fetch origin` e `git rev-parse HEAD` == `git rev-parse origin/<branch>`; se diferir, **pare**.

## Passo 2 — PR da branch de trabalho → develop

1. Aplique a regra de PR já aberto (head `<branch>`, base `develop`).
2. Leia os commits da branch (`git log --no-merges --format='%s%n%b' origin/develop..HEAD`) e o template `.github/pull_request_template.md`.
3. Título em Conventional Commits derivado dos commits (vira a mensagem do squash merge). Corpo = template preenchido, em inglês como o template: `Summary`, `Type of change` e `Checklist` marcados conforme o que foi verificado, `How to test` com passos concretos; remova `Closes #` se não houver issue e a seção de screenshots se não houver mudança de UI.
   ```bash
   gh pr create --repo ROM-mm/Notisbook --base develop --head <branch> --title "<título>" --body "<corpo>"
   ```
4. Mostre a URL. Peça o merge com **Squash and merge** e pergunte, sozinho na mensagem: **"Merge feito?"** Confirme `MERGED`.

## Passo 3 — atualizar a develop

```bash
git checkout develop
git pull --ff-only
```

## Passo 4 — PR develop → main

1. Aplique a regra de PR já aberto (head `develop`, base `main`).
2. Leia o que entra (`git log --no-merges --format='%s' origin/main..origin/develop`).
3. Título `release: develop → main (<resumo>)`. Corpo em pt-BR, no modelo do PR #11: `## Resumo` (PRs que entram, com o número), `## Impacto para quem atualiza` (ações manuais, migrações, pendências conhecidas) e `## Como testar`.
   ```bash
   gh pr create --repo ROM-mm/Notisbook --base main --head develop --title "release: develop → main (<resumo>)" --body "<corpo>"
   ```
4. Mostre a URL. Peça o merge com **Create a merge commit** (não squash: o cálculo da versão no Passo 6 lê os commits da `develop` no histórico da `main`). Pergunte, sozinho na mensagem: **"Merge feito?"** Confirme `MERGED`.

## Passo 5 — atualizar a main

```bash
git checkout main
git pull --ff-only
```

## Passo 6 — versão e CHANGELOG

1. Leia o estado:
   ```bash
   git fetch origin --tags
   git describe --tags --abbrev=0
   grep -m1 '^version' backend/pyproject.toml
   git log --no-merges --format='%s' "$(git describe --tags --abbrev=0)"..HEAD
   ```
2. Leia o `CHANGELOG.md`. Formato: Keep a Changelog, seções `### Added` / `### Changed` / `### Fixed`, cada item com uma frase-resumo em **negrito** seguida de prosa, sem hash de commit e sem "Full Changelog". Use exemplos concretos, nunca placeholders. Confira no código qualquer número publicado.
3. Decida a versão:
   - Se o topo do CHANGELOG já tem uma seção `## [X.Y.Z]` **maior** que a versão de `backend/pyproject.toml` e que a última tag, ela é a versão: só acrescente o que estiver em `## [Unreleased]` e o que os commits desde a última tag trouxerem e ainda não estiver descrito.
   - Senão, calcule pelos commits desde a última tag (versão `0.x`): algum `feat` ou `BREAKING CHANGE` → sobe o minor (`0.3.0` → `0.4.0`); só `fix`/`perf`/`refactor`/`docs`/`chore` → sobe o patch (`0.3.0` → `0.3.1`). Depois da `1.0.0`, `BREAKING CHANGE` sobe o major.
   - Sem commit novo desde a última tag e sem conteúdo em `## [Unreleased]`: avise que não há o que publicar e **pare**.
4. Obtenha a data com `date +%F` (nunca de memória) e escreva `## [X.Y.Z] - AAAA-MM-DD` logo abaixo de `## [Unreleased]`, com uma linha de resumo da versão e os itens agrupados. Mova para ela o conteúdo de `## [Unreleased]` e deixe `## [Unreleased]` vazio.
5. Mostre a versão e o motivo (ex.: "0.4.0 — há 2 commits `feat` desde v0.3.0"), um resumo curto em português do que entrou e `git status --porcelain`. Se houver alteração fora do `CHANGELOG.md`, **pare** e mostre-a.
6. Pergunte, sozinho na mensagem: **"Pode commitar?"** Com `sim`:
   ```bash
   git add -- CHANGELOG.md
   git commit -m "docs(changelog): add X.Y.Z release notes"
   ```
7. Peça ao operador para rodar `git push origin main` e responder quando terminar. Confira com `git fetch origin` e `git rev-parse main` == `git rev-parse origin/main`; se diferir, **pare**.

## Passo 7 — testes locais (manuais, do operador)

Liste para o operador rodar, nesta ordem:

```bash
./scripts/release.sh --dry-run X.Y.Z
./scripts/release.sh --local-install X.Y.Z
```

O dry-run deve terminar com `Dry-run de vX.Y.Z concluído (nada foi alterado)` e sem `ERRO:`/`AVISO:`. Pergunte, sozinho na mensagem: **"Os dois testes concluíram OK?"** Qualquer resposta que não seja `sim` **encerra** o comando.

## Passo 8 — release oficial (manual, do operador)

Peça ao operador para rodar `./scripts/release.sh X.Y.Z` (o script grava a versão, commita `chore(release): vX.Y.Z`, cria a tag, compila, faz o push e cria a release). Pergunte, sozinho na mensagem: **"A release concluiu?"** Com `sim`, confira:

```bash
gh release view vX.Y.Z --repo ROM-mm/Notisbook --json tagName,isDraft,url,publishedAt,assets --jq '{tag: .tagName, rascunho: .isDraft, url: .url, publicada: .publishedAt, assets: [.assets[].name]}'
gh release list --repo ROM-mm/Notisbook --limit 3
```

Exija tag `vX.Y.Z`, `rascunho: false`, a vX.Y.Z marcada como `Latest` na lista e os assets presentes. Termine com: **"vX.Y.Z publicada no GitHub: <url>"** e a lista de assets. Qualquer divergência: mostre-a e **pare**.

## Passo 9 — limpeza

Sugira rodar `/clean` para remover os resíduos de build. A decisão é do operador; este comando não apaga nada.

## Passo 10 — sincronizar a develop com a main

1. Atualize a main (traz o commit `chore(release): vX.Y.Z`):
   ```bash
   git checkout main
   git pull --ff-only
   ```
2. Aplique a regra de PR já aberto (head `main`, base `develop`) e abra:
   ```bash
   gh pr create --repo ROM-mm/Notisbook --base develop --head main --title "chore(release): sincroniza develop com vX.Y.Z" --body "<resumo em pt-BR: traz o CHANGELOG e o bump da vX.Y.Z da main para a develop>"
   ```
3. Mostre a URL. Peça o merge com **Create a merge commit** e pergunte, sozinho na mensagem: **"Merge feito?"** Confirme `MERGED`.
4. Atualize a develop e confira:
   ```bash
   git checkout develop
   git pull --ff-only
   git fetch origin
   git diff --stat origin/main origin/develop
   ```
   O diff deve sair vazio. Se não sair, mostre-o e **pare**. Vazio: termine com **"develop sincronizada com a main na vX.Y.Z."**
