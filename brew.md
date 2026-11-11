# Publicando o Notisbook no Homebrew

Guia para publicar o Notisbook num **tap próprio** do Homebrew, de modo que
outros devs instalem com:

```bash
brew install rom-mm/tap/notisbook
notisbook
```

O pacote Python já está pronto para isso. Este guia cobre o que fica do lado do
mantenedor: release no GitHub, repositório do tap e a fórmula.

## Visão geral

| peça | onde vive | quem gera |
|------|-----------|-----------|
| código do app | `github.com/ROM-mm/Notisbook` | este repositório |
| sdist (`notisbook-<versão>.tar.gz`) com o frontend embutido | asset da release no GitHub | `scripts/build_release.py` |
| fórmula `notisbook.rb` | `github.com/ROM-mm/homebrew-tap` | mantenedor |

> A fórmula baixa o **sdist anexado à release**, nunca o "Source code" automático
> do GitHub — esse tarball levaria `.claude/`, `.idea/` e notas internas, e não
> traz o frontend compilado.

## Pré-requisitos (máquina do mantenedor)

- macOS com [Homebrew](https://brew.sh)
- [uv](https://docs.astral.sh/uv/) e Python 3.12+
- Node.js + npm (para compilar o frontend)
- [GitHub CLI](https://cli.github.com) (`gh`) autenticado, opcional mas prático
- Repositório `ROM-mm/Notisbook` **público** (o tap baixa sem token)

## 1. Gerar os artefatos da release

Na raiz deste repositório:

```bash
uv run --project backend python scripts/build_release.py
```

O script:

1. roda `npm ci` e `npm run build` em `frontend/`;
2. copia `frontend/dist` para `backend/src/notisbook/_frontend/`;
3. gera `backend/dist/notisbook-<versão>.tar.gz` (sdist) e o `.whl`;
4. confere que os dois contêm `notisbook/_frontend/index.html`;
5. imprime o **sha256 do sdist** — guarde esse valor para a fórmula.

A versão vem de `backend/pyproject.toml` (`version = "0.1.0"`).

Conferências rápidas:

```bash
shasum -a 256 backend/dist/notisbook-0.1.0.tar.gz      # mesmo hash impresso pelo script
tar -tzf backend/dist/notisbook-0.1.0.tar.gz | grep -E '\.claude|\.idea|\.iml|_cache'   # deve sair vazio
```

## 2. Publicar a release no GitHub

```bash
git push origin main
git tag v0.1.0
git push origin v0.1.0
gh release create v0.1.0 backend/dist/notisbook-0.1.0.tar.gz \
  --title "Notisbook 0.1.0" --notes "Primeira release distribuída via Homebrew"
```

URL do asset (é a `url` da fórmula):

```
https://github.com/ROM-mm/Notisbook/releases/download/v0.1.0/notisbook-0.1.0.tar.gz
```

## 3. Criar o tap

O repositório **precisa** se chamar `homebrew-<nome>`; com `homebrew-tap`, o
tap vira `rom-mm/tap`.

```bash
brew tap-new rom-mm/tap          # cria o esqueleto local (inclui workflow de CI)
gh repo create ROM-mm/homebrew-tap --public --source "$(brew --repository rom-mm/tap)" --push
```

## 4. Escrever a fórmula

Arquivo `Formula/notisbook.rb` no tap. É uma fórmula de aplicativo Python
padrão do Homebrew, com estes elementos:

| elemento | valor |
|----------|-------|
| `include` | `Language::Python::Virtualenv` |
| `desc` / `homepage` | "Local notebook UI and Spark environment manager" / `https://github.com/ROM-mm/Notisbook` |
| `url` / `sha256` | URL do asset da release / hash impresso pelo `build_release.py` |
| `license` | `"Apache-2.0"` |
| `depends_on "python@3.12"` | runtime do app |
| `depends_on "openjdk@17"` | JDK do Spark 3.x (Spark 4.x prefere 21: acrescente `openjdk@21` se quiser cobrir) |
| `depends_on "rust" => :build` | algumas dependências são compiladas a partir do código-fonte e precisam de Rust (`pydantic-core`, `nh3`, `watchfiles`, `rpds-py`) |
| `resource` | um bloco por dependência Python (ver abaixo) |
| `install` | `virtualenv_install_with_resources` |
| `test` | `notisbook --version` deve imprimir a versão |

**Blocos `resource`:** não escreva à mão. Crie a fórmula sem eles e gere-os com:

```bash
brew update-python-resources rom-mm/tap/notisbook
```

**JDK:** o Notisbook encontra o JDK sozinho, nesta ordem — `$JAVA_HOME` (se for
da versão certa), `/usr/libexec/java_home -v <major>` e, por último, o keg
`$(brew --prefix)/opt/openjdk@<major>`. Como o `openjdk@17` do Homebrew é
keg-only, essa última busca é o que faz a dependência da fórmula funcionar sem
nenhum passo extra do usuário.

## 5. Validar antes de divulgar

```bash
brew install --build-from-source rom-mm/tap/notisbook
brew test rom-mm/tap/notisbook
brew audit --strict --new rom-mm/tap/notisbook
notisbook --version      # 0.1.0
notisbook                # abre a UI no navegador
```

Depois, faça commit e push da fórmula no `homebrew-tap`.

## 6. Instalação para outros devs

```bash
brew install rom-mm/tap/notisbook
notisbook
```

Atualizações: `brew update && brew upgrade notisbook`.

## 7. Publicando uma versão nova

1. Atualize `version` em `backend/pyproject.toml`.
2. Rode `uv run --project backend python scripts/build_release.py` e anote o sha256.
3. Crie a tag e a release `v<versão>` com o novo sdist anexado.
4. No tap, atualize `url` e `sha256` da fórmula
   (`brew bump-formula-pr --url <url> --sha256 <sha> rom-mm/tap/notisbook` faz isso).
5. Se dependências Python mudaram, rode `brew update-python-resources` de novo.
6. Valide (passo 5) e faça push do tap.

## Observações

- O sha256 muda sempre que o conteúdo do sdist muda — use o hash do artefato
  que foi de fato anexado à release.
- `--skip-npm-ci` no `build_release.py` existe só para desenvolvimento; a
  release deve rodar com `npm ci`.
- Dados locais do app ficam em `~/.notisbook` (ou `NOTISBOOK_HOME`); o servidor
  escuta só em `127.0.0.1:8765`.
- Fora deste guia: publicar no PyPI e enviar ao `homebrew-core`.
