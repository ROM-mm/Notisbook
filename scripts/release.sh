#!/usr/bin/env bash
# Publica uma versão do Notisbook: versão + tag + build + release no GitHub
# e fórmula atualizada/validada/publicada no tap Homebrew (rom-mm/tap).
# Uso: ./scripts/release.sh [--dry-run] [--skip-brew-test] <versão X.Y.Z>
set -euo pipefail

REPO_SLUG="ROM-mm/Notisbook"
TAP_NAME="rom-mm/tap"
FORMULA_REF="rom-mm/tap/notisbook"
FORMULA_REL="Formula/notisbook.rb"

DRY_RUN=0
SKIP_BREW_TEST=0
VERSION=""

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORKDIR=""
ETAPA="conferências"
PUSH_FEITO=0
RELEASE_CRIADA=0
ATUALIZAR_RESOURCES=0

uso() {
  cat <<EOF
Uso: scripts/release.sh [--dry-run] [--skip-brew-test] <versão>

Publica o Notisbook <versão> (formato X.Y.Z) no GitHub e atualiza o tap Homebrew.

Opções:
  --dry-run          executa só as conferências e imprime os comandos de
                     escrita/push/release sem executá-los
  --skip-brew-test   pula brew reinstall/test/audit antes de publicar o tap
  -h, --help         mostra esta ajuda
EOF
}

info() { printf '==> %s\n' "$*"; }
aviso() { printf 'AVISO: %s\n' "$*" >&2; }
die() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

# Executa o comando; em --dry-run apenas o imprime.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] %s\n' "$*"
  else
    printf '$ %s\n' "$*"
    "$@"
  fi
}

limpar() {
  local codigo=$?
  if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
    rm -rf "$WORKDIR"
  fi
  if [ "$codigo" -ne 0 ] && [ "$DRY_RUN" -eq 0 ] && [ "$ETAPA" != "conferências" ]; then
    {
      printf '\nFalha na etapa: %s (exit %s).\n' "$ETAPA" "$codigo"
      if [ "$RELEASE_CRIADA" -eq 1 ]; then
        printf 'A release v%s JÁ FOI publicada em %s; o tap NÃO foi publicado.\n' "$VERSION" "$REPO_SLUG"
        if [ "$(git -C "$TAP" rev-list --count origin/main..main 2>/dev/null || echo 0)" -gt 0 ]; then
          printf 'O commit do tap já existe localmente; só falta enviá-lo: git -C %s push origin main\n' "$TAP"
        else
          printf 'Para retomar: corrija o problema, ajuste/valide a fórmula no tap e faça commit+push manual de %s.\n' "$FORMULA_REL"
          if ! git -C "$TAP" diff --quiet HEAD -- "$FORMULA_REL" 2>/dev/null; then
            printf 'Para descartar a edição da fórmula: git -C %s checkout HEAD -- %s\n' "$TAP" "$FORMULA_REL"
          fi
        fi
        printf 'Não rode o script de novo para a mesma versão (a tag/release existe e ele aborta).\n'
      elif [ "$PUSH_FEITO" -eq 1 ]; then
        printf 'O commit e a tag %s JÁ FORAM publicados em origin; a release pode não existir ou estar sem o asset. Não apague tag nem commit.\n' "$TAG"
        printf 'Confira: gh release view %s --repo %s\n' "$TAG" "$REPO_SLUG"
        printf 'Se a release existir sem os assets (builds em %s e %s):\n' "$ROOT/$ASSET_PATH" "$ROOT/$MINIO_DIST"
        printf '  gh release upload %s %s %s/*.tar.gz --repo %s --clobber\n' "$TAG" "$ROOT/$ASSET_PATH" "$ROOT/$MINIO_DIST" "$REPO_SLUG"
        printf 'Se não existir (a partir da raiz do repo):\n'
        printf '  cd %q\n' "$ROOT"
        printf '  %q' "${CMD_RELEASE[@]}"; printf '\n'
        printf 'Depois siga com o tap manualmente: sha256 do asset, url/sha256 em %s, scripts/gen_formula_minio.py (resources do MinIO), brew reinstall/test/audit, commit+push.\n' "$FORMULA_REL"
      else
        printf 'Nada foi enviado ao remoto (o push é atômico); confirme com git ls-remote --tags origin %s.\n' "$TAG"
        printf 'Para restaurar o estado local (as conferências garantiram árvore limpa e main == origin/main):\n'
        if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
          printf '  git tag -d %s\n' "$TAG"
        fi
        printf '  git reset --hard origin/main\n'
      fi
    } >&2
  fi
  return "$codigo"
}
trap limpar EXIT

# Argumentos
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --skip-brew-test) SKIP_BREW_TEST=1 ;;
    -h|--help) uso; exit 0 ;;
    -*) uso >&2; die "opção desconhecida: $1" ;;
    *)
      [ -z "$VERSION" ] || { uso >&2; die "versão informada mais de uma vez"; }
      VERSION="$1"
      ;;
  esac
  shift
done

[ -n "$VERSION" ] || { uso >&2; die "versão obrigatória (X.Y.Z)"; }
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  uso >&2
  die "versão inválida '$VERSION': use o formato X.Y.Z"
fi

TAG="v$VERSION"
ASSET="notisbook-$VERSION.tar.gz"
ASSET_PATH="backend/dist/$ASSET"
ASSET_URL="https://github.com/$REPO_SLUG/releases/download/$TAG/$ASSET"
# notislake: tarballs do minio/mc compilados por scripts/build_minio.py (saem em backend/dist, ignorado pelo git)
MINIO_MANIFEST="backend/src/notisbook/notislake/minio_manifest.json"
MINIO_DIST="backend/dist/notislake"
# Mesmo comando na publicação e na orientação de retomada (limpar)
CMD_RELEASE=(gh release create "$TAG" "$ASSET_PATH" --repo "$REPO_SLUG"
  --title "Notisbook $VERSION" --generate-notes --verify-tag)

[ "$DRY_RUN" -eq 1 ] && info "Modo --dry-run: nada será alterado."

# Conferências (nenhuma escrita antes de todas passarem)
info "Conferindo pré-requisitos"
for cmd in git gh uv npm brew curl shasum python3; do
  command -v "$cmd" >/dev/null 2>&1 || die "comando não encontrado: $cmd"
done
# O build do notislake roda num container; em --dry-run nada é compilado
if [ "$DRY_RUN" -eq 0 ]; then
  command -v docker >/dev/null 2>&1 || die "comando não encontrado: docker"
  docker info >/dev/null 2>&1 || die "docker indisponível (daemon parado?)"
fi

cd "$ROOT"
[ "$(git rev-parse --show-toplevel)" = "$ROOT" ] || die "$ROOT não é a raiz de um repositório git próprio"
[ -f scripts/build_release.py ] && [ -f scripts/gen_formula_minio.py ] && [ -f backend/pyproject.toml ] && [ -f frontend/package.json ] \
  || die "$ROOT não parece a raiz do Notisbook-app"

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "main" ] || die "branch atual é '$branch'; a release sai de 'main'"

# .claude/ está no .gitignore, então não entra no porcelain
[ -z "$(git status --porcelain)" ] || die "árvore de trabalho suja; faça commit ou stash antes"

git fetch origin
if [ "$(git rev-parse main)" != "$(git rev-parse origin/main)" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    aviso "main difere de origin/main (commits não enviados?); em release real isto aborta"
  else
    die "main local difere de origin/main; sincronize antes de publicar"
  fi
fi

gh auth status >/dev/null 2>&1 || die "gh não autenticado (gh auth login)"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  die "a tag $TAG já existe localmente"
fi
remote_tag="$(git ls-remote --tags origin "refs/tags/$TAG")"
[ -z "$remote_tag" ] || die "a tag $TAG já existe no remoto origin"
if gh release view "$TAG" --repo "$REPO_SLUG" >/dev/null 2>&1; then
  die "a release $TAG já existe em $REPO_SLUG"
fi

# A nova versão precisa ser maior que a atual (campo a campo; 10# evita octal)
versao_maior() {
  local n1 n2 n3 a1 a2 a3
  IFS=. read -r n1 n2 n3 <<<"$1"
  IFS=. read -r a1 a2 a3 <<<"$2"
  if (( 10#$n1 != 10#$a1 )); then (( 10#$n1 > 10#$a1 )); return; fi
  if (( 10#$n2 != 10#$a2 )); then (( 10#$n2 > 10#$a2 )); return; fi
  (( 10#$n3 > 10#$a3 ))
}
versao_atual="$(awk -F'"' '/^version = "/ { print $2; exit }' backend/pyproject.toml)"
[[ "$versao_atual" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "não consegui ler a versão atual em backend/pyproject.toml"
versao_maior "$VERSION" "$versao_atual" || die "a versão $VERSION deve ser maior que a atual $versao_atual"

TAP="$(brew --repository "$TAP_NAME")"
[ -d "$TAP" ] || die "tap local não encontrado: $TAP"
TAP="$(cd "$TAP" && pwd -P)"
# Sem repo próprio o git subiria para o repositório do Homebrew
tap_top="$(git -C "$TAP" rev-parse --show-toplevel 2>/dev/null || true)"
[ "$tap_top" = "$TAP" ] || die "o tap $TAP não é um repositório git próprio"
[ -f "$TAP/$FORMULA_REL" ] || die "fórmula ausente: $TAP/$FORMULA_REL"
[ -z "$(git -C "$TAP" status --porcelain)" ] || die "tap com alterações locais: $TAP"
[ "$(git -C "$TAP" rev-parse --abbrev-ref HEAD)" = "main" ] || die "o tap não está na branch main"
git -C "$TAP" fetch origin
[ "$(git -C "$TAP" rev-parse main)" = "$(git -C "$TAP" rev-parse origin/main)" ] \
  || die "main do tap difere de origin/main; sincronize antes de publicar"

info "Conferências ok para $TAG"

# Temporários ficam aqui dentro; o trap limpar remove o diretório inteiro
WORKDIR="$(mktemp -d)"

# Versão, commit e tag
ETAPA="versão"
info "Gravando versão $VERSION"
if [ "$DRY_RUN" -eq 1 ]; then
  printf '[dry-run] atualizar version = "%s" em backend/pyproject.toml\n' "$VERSION"
else
  # Troca só a primeira linha `version = "..."` (a do [project])
  tmp_toml="$WORKDIR/pyproject.toml"
  awk -v v="$VERSION" '!feito && /^version = "/ { print "version = \"" v "\""; feito=1; next } { print }' \
    backend/pyproject.toml >"$tmp_toml"
  cat "$tmp_toml" >backend/pyproject.toml
  grep -q "^version = \"$VERSION\"$" backend/pyproject.toml || die "falha ao gravar a versão em backend/pyproject.toml"
fi
# uv.lock registra a versão do próprio projeto, então precisa acompanhar
run uv lock --project backend
(cd frontend && run npm version "$VERSION" --no-git-tag-version)
run git add -- backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json
run git commit -m "chore(release): $TAG"
run git tag -a "$TAG" -m "Notisbook $VERSION"

# D6: resources só são regenerados se as dependências mudaram desde a tag anterior.
# Decidido antes do push para que uma falha aqui ainda não tenha publicado nada.
lock_normalizado() {
  # Ignora a linha de versão do próprio notisbook, que muda a cada release
  git show "$1:backend/uv.lock" | awk '
    skip && /^version = / { skip=0; next }
    { skip = ($0 == "name = \"notisbook\"") ; print }
  '
}
if [ "$DRY_RUN" -eq 1 ]; then ref_nova="HEAD"; ref_base="HEAD"; else ref_nova="$TAG"; ref_base="$TAG^"; fi
tag_anterior="$(git describe --tags --abbrev=0 --match 'v[0-9]*' "$ref_base")"
lock_ant="$(lock_normalizado "$tag_anterior")"
lock_novo="$(lock_normalizado "$ref_nova")"
if [ "$lock_ant" != "$lock_novo" ]; then
  ATUALIZAR_RESOURCES=1
  info "backend/uv.lock mudou desde $tag_anterior: resources serão regenerados"
else
  info "backend/uv.lock inalterado desde $tag_anterior: resources serão mantidos"
fi

# Build
ETAPA="build"
info "Gerando build"
run uv run --project backend python scripts/build_release.py
if [ "$DRY_RUN" -eq 0 ] && [ ! -f "$ASSET_PATH" ]; then
  die "artefato esperado não encontrado: $ASSET_PATH"
fi

# notislake: antes do push, para que uma falha aqui ainda não tenha publicado nada
ETAPA="build notislake"
info "Compilando os binários do notislake"
MINIO_NAMES=()
MINIO_SHAS=()
while read -r nome sha; do
  MINIO_NAMES+=("$nome")
  MINIO_SHAS+=("$sha")
done < <(python3 -c 'import json, sys
for _, a in sorted(json.load(open(sys.argv[1]))["archs"].items()):
    print(a["tarball"], a["sha256"])' "$MINIO_MANIFEST")
[ "${#MINIO_NAMES[@]}" -gt 0 ] || die "nenhum tarball listado em $MINIO_MANIFEST"
# Criação da release e envio dos tarballs num passo só: não há estado "release sem os binários"
for nome in "${MINIO_NAMES[@]}"; do
  CMD_RELEASE+=("$MINIO_DIST/$nome")
done
if [ "$DRY_RUN" -eq 0 ]; then
  rm -rf "$MINIO_DIST"
fi
run uv run --project backend python scripts/build_minio.py --out "$MINIO_DIST"
if [ "$DRY_RUN" -eq 0 ]; then
  # O build regrava o manifesto; ele precisa já estar commitado e igual ao que foi compilado
  git diff --quiet -- "$MINIO_MANIFEST" || die "$MINIO_MANIFEST mudou após o build; revise, faça commit e rode a release de novo"
  for i in "${!MINIO_NAMES[@]}"; do
    [ -f "$MINIO_DIST/${MINIO_NAMES[$i]}" ] || die "tarball esperado não encontrado: $MINIO_DIST/${MINIO_NAMES[$i]}"
    # A fórmula usa o sha do manifesto; o arquivo publicado precisa bater com ele
    sha_arquivo="$(shasum -a 256 "$MINIO_DIST/${MINIO_NAMES[$i]}" | awk '{print $1}')"
    [ "$sha_arquivo" = "${MINIO_SHAS[$i]}" ] \
      || die "sha256 de ${MINIO_NAMES[$i]} difere do manifesto ($sha_arquivo != ${MINIO_SHAS[$i]})"
  done
fi

# Gera a fórmula só para validar a entrada, antes do push (em --dry-run também: lê o tap e escreve no WORKDIR)
python3 scripts/gen_formula_minio.py --formula "$TAP/$FORMULA_REL" --manifest "$MINIO_MANIFEST" \
  --repo "$REPO_SLUG" --tag "$TAG" --out "$WORKDIR/notisbook.check.rb" \
  || die "a fórmula do tap não aceita a geração do MinIO (scripts/gen_formula_minio.py)"

# Push e release
ETAPA="push/release"
info "Publicando commit, tag e release"
run git push --atomic origin main "$TAG"
PUSH_FEITO=1
run "${CMD_RELEASE[@]}"
RELEASE_CRIADA=1

# sha256 do asset publicado
ETAPA="sha256"
info "Calculando sha256 do asset baixado"
if [ "$DRY_RUN" -eq 1 ]; then
  printf '[dry-run] curl -fL %s e shasum -a 256\n' "$ASSET_URL"
  SHA="<sha256-do-asset>"
else
  # --retry-all-errors: logo após o upload o asset pode responder 404 por instantes
  curl -fsSL --retry 3 --retry-all-errors -o "$WORKDIR/$ASSET" "$ASSET_URL"
  SHA="$(shasum -a 256 "$WORKDIR/$ASSET" | awk '{print $1}')"
  [[ "$SHA" =~ ^[0-9a-f]{64}$ ]] || die "sha256 inválido: $SHA"
  echo "sha256: $SHA"
fi

# Fórmula no tap
ETAPA="fórmula"
info "Atualizando $FORMULA_REL no tap"
FORMULA="$TAP/$FORMULA_REL"
if [ "$DRY_RUN" -eq 1 ]; then
  printf '[dry-run] atualizar url/sha256 principais e resources do MinIO em %s (url=%s)\n' "$FORMULA" "$ASSET_URL"
else
  tmp_rb="$WORKDIR/notisbook.rb"
  # Só a primeira ocorrência de cada (os blocos resource ficam indentados mais fundo)
  awk -v url="$ASSET_URL" -v sha="$SHA" '
    !u && /^  url "/    { print "  url \"" url "\""; u=1; next }
    !s && /^  sha256 "/ { print "  sha256 \"" sha "\""; s=1; next }
    { print }
    END { if (!u || !s) exit 1 }
  ' "$FORMULA" >"$tmp_rb" || die "url/sha256 principais não encontrados na fórmula"
  # Resources do MinIO (url do asset + sha do manifesto), instalação e env NOTISBOOK_MINIO_DIST
  python3 scripts/gen_formula_minio.py --formula "$tmp_rb" --manifest "$MINIO_MANIFEST" \
    --repo "$REPO_SLUG" --tag "$TAG" --out "$WORKDIR/notisbook.minio.rb" \
    || die "falha ao gerar os resources do MinIO na fórmula"
  cat "$WORKDIR/notisbook.minio.rb" >"$FORMULA"
fi

# Sem auto-update o brew não mexe no tap/fórmula durante os comandos abaixo
export HOMEBREW_NO_AUTO_UPDATE=1

# D6: decisão tomada antes do push
if [ "$ATUALIZAR_RESOURCES" -eq 1 ]; then
  ETAPA="resources"
  run brew update-python-resources "$FORMULA_REF"
fi

# Validação
if [ "$SKIP_BREW_TEST" -eq 1 ]; then
  aviso "validação brew pulada (--skip-brew-test)"
else
  ETAPA="validação brew"
  info "Validando a fórmula"
  validar() {
    run brew reinstall --build-from-source "$FORMULA_REF" \
      && run brew test "$FORMULA_REF" \
      && run brew audit --strict "$FORMULA_REF"
  }
  # A orientação de falha sai uma vez só, no trap limpar
  validar || exit 1
fi

# Publicação do tap
ETAPA="tap"
info "Publicando o tap"
run git -C "$TAP" add -- "$FORMULA_REL"
run git -C "$TAP" commit -m "notisbook $VERSION"
run git -C "$TAP" push origin main

ETAPA="concluído"
echo
if [ "$DRY_RUN" -eq 1 ]; then info "Dry-run de $TAG concluído (nada foi alterado)"; else info "Release $TAG concluída"; fi
echo "  release: https://github.com/$REPO_SLUG/releases/tag/$TAG"
echo "  tap:     $TAP_NAME ($FORMULA_REL)"
echo "Para instalar/atualizar:"
echo "  brew update && brew upgrade notisbook"
