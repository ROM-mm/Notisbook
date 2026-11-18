#!/usr/bin/env bash
# Publica uma versão do Notisbook: versão + tag + build + release no GitHub
# com wheel, constraints, binários do MinIO, SHA256SUMS e install.sh.
# Uso: ./scripts/release.sh [--dry-run] <versão X.Y.Z>
set -euo pipefail

REPO_SLUG="ROM-mm/Notisbook"

DRY_RUN=0
VERSION=""

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORKDIR=""
ETAPA="conferências"
PUSH_FEITO=0

uso() {
  cat <<EOF
Uso: scripts/release.sh [--dry-run] <versão>

Publica o Notisbook <versão> (formato X.Y.Z) no GitHub (wheel, constraints,
binários do MinIO, SHA256SUMS e install.sh).

Opções:
  --dry-run          executa só as conferências e imprime os comandos de
                     escrita/push/release sem executá-los
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
  local notas_salvas=""
  # Pós-push, as notas precisam sobreviver à remoção do WORKDIR para a retomada manual
  if [ "$codigo" -ne 0 ] && [ "$DRY_RUN" -eq 0 ] && [ "$PUSH_FEITO" -eq 1 ] && [ -f "${NOTES_FILE:-}" ]; then
    notas_salvas="$ROOT/backend/dist/release-notes-$TAG.md"
    mkdir -p "$ROOT/backend/dist" && cp "$NOTES_FILE" "$notas_salvas" || notas_salvas=""
  fi
  if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
    rm -rf "$WORKDIR"
  fi
  if [ "$codigo" -ne 0 ] && [ "$DRY_RUN" -eq 0 ] && [ "$ETAPA" != "conferências" ]; then
    {
      printf '\nFalha na etapa: %s (exit %s).\n' "$ETAPA" "$codigo"
      if [ "$PUSH_FEITO" -eq 1 ]; then
        printf 'O commit e a tag %s JÁ FORAM publicados em origin; a release pode não existir ou estar incompleta. Não apague tag nem commit.\n' "$TAG"
        printf 'Confira: gh release view %s --repo %s\n' "$TAG" "$REPO_SLUG"
        printf 'Se a release existir com assets faltando (builds em %s):\n' "$ROOT/backend/dist"
        printf '  cd %q\n' "$ROOT"
        printf '  gh release upload %s' "$TAG"; printf ' %q' "${CMD_RELEASE[@]:4:$N_ASSETS}"; printf ' --repo %s --clobber\n' "$REPO_SLUG"
        printf 'Se não existir (a partir da raiz do repo):\n'
        if [ -n "$notas_salvas" ]; then
          printf '  (notas da release salvas em %s)\n' "$notas_salvas"
        else
          printf '  (não foi possível salvar as notas: recrie o arquivo com o corpo da seção "## [%s]" do CHANGELOG.md e ajuste --notes-file)\n' "$VERSION"
        fi
        printf '  cd %q\n' "$ROOT"
        printf ' '
        for arg in "${CMD_RELEASE[@]}"; do
          if [ -n "$notas_salvas" ] && [ "$arg" = "$NOTES_FILE" ]; then arg="$notas_salvas"; fi
          printf ' %q' "$arg"
        done
        printf '\n'
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
# notislake: tarballs do minio/mc compilados por scripts/build_minio.py (saem em backend/dist, ignorado pelo git)
MINIO_MANIFEST="backend/src/notisbook/notislake/minio_manifest.json"
MINIO_DIST="backend/dist/notislake"
DIST="backend/dist"
CONSTRAINTS_PATH="$DIST/constraints-$VERSION.txt"
SUMS_PATH="$DIST/SHA256SUMS"
INSTALL_SH="install.sh"
# Preenchidos após o build; limpar() os usa na orientação de retomada
CMD_RELEASE=()
N_ASSETS=0

[ "$DRY_RUN" -eq 1 ] && info "Modo --dry-run: nada será alterado."

# Conferências (nenhuma escrita antes de todas passarem)
info "Conferindo pré-requisitos"
for cmd in git gh uv npm shasum python3; do
  command -v "$cmd" >/dev/null 2>&1 || die "comando não encontrado: $cmd"
done
# O build do notislake roda num container; em --dry-run nada é compilado
if [ "$DRY_RUN" -eq 0 ]; then
  command -v docker >/dev/null 2>&1 || die "comando não encontrado: docker"
  docker info >/dev/null 2>&1 || die "docker indisponível (daemon parado?)"
fi

cd "$ROOT"
[ "$(git rev-parse --show-toplevel)" = "$ROOT" ] || die "$ROOT não é a raiz de um repositório git próprio"
[ -f scripts/build_release.py ] && [ -f scripts/build_minio.py ] && [ -f "$INSTALL_SH" ] && [ -f backend/pyproject.toml ] && [ -f frontend/package.json ] \
  || die "$ROOT não parece a raiz do Notisbook-app"

# Notas da release: corpo da seção "## [X.Y.Z]" do CHANGELOG.md, sem o cabeçalho,
# sem as definições de rodapé "[X.Y.Z]: url" / "[Unreleased]: url" e sem linhas em
# branco nas pontas. A seção termina em qualquer título "# " ou "## " fora de bloco
# de código; dentro de cercas (``` ou ~~~) tudo é mantido. index() compara a versão
# literalmente. Outras definições "[x]: url" ficam, pois o corpo pode referenciá-las.
extrair_notas() {
  awk -v v="$VERSION" '
    function emite(l) {
      if (l ~ /^[[:space:]]*$/) { if (iniciou) vazias = vazias l "\n"; return }
      iniciou = 1; printf "%s", vazias; vazias = ""; print l
    }
    /^(```|~~~)/ { cerca = !cerca; if (dentro) emite($0); next }
    cerca { if (dentro) emite($0); next }
    /^##? / { if (dentro) exit; dentro = (index($0, "## [" v "]") == 1); next }
    /^\[[vV]?[0-9]+\.[0-9]+\.[0-9]+[^]]*\]: / || tolower($0) ~ /^\[unreleased\]: / { next }
    dentro { emite($0) }
  ' CHANGELOG.md
}
[ -f CHANGELOG.md ] || die "CHANGELOG.md não encontrado em $ROOT; a release usa a seção da versão como notas"
NOTAS="$(extrair_notas)" || die "falha ao ler CHANGELOG.md"
[ -n "$NOTAS" ] || die "CHANGELOG.md sem a seção '## [$VERSION]' ou com a seção vazia; escreva as notas antes de publicar"
if [ "$DRY_RUN" -eq 1 ]; then
  info "Notas da release $TAG (extraídas do CHANGELOG.md)"
  printf '%s\n' "$NOTAS"
fi

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

info "Conferências ok para $TAG"

# Temporários ficam aqui dentro; o trap limpar remove o diretório inteiro
WORKDIR="$(mktemp -d)"
NOTES_FILE="$WORKDIR/release-notes.md"
printf '%s\n' "$NOTAS" >"$NOTES_FILE"

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

# Build
ETAPA="build"
info "Gerando build"
run uv run --project backend python scripts/build_release.py
if [ "$DRY_RUN" -eq 1 ]; then
  WHEEL_PATH="$DIST/notisbook-$VERSION-<tags-da-wheel>.whl"
else
  wheels=("$DIST"/notisbook-"$VERSION"-*.whl)
  [ "${#wheels[@]}" -eq 1 ] && [ -f "${wheels[0]}" ] || die "esperava exatamente uma wheel de $VERSION em $DIST"
  WHEEL_PATH="${wheels[0]}"
  [ -f "$CONSTRAINTS_PATH" ] || die "artefato esperado não encontrado: $CONSTRAINTS_PATH"
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
MINIO_ASSETS=()
for nome in "${MINIO_NAMES[@]}"; do
  MINIO_ASSETS+=("$DIST/$nome")
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
    # O install.sh valida o tarball pelo SHA256SUMS; o arquivo publicado precisa bater com o manifesto
    sha_arquivo="$(shasum -a 256 "$MINIO_DIST/${MINIO_NAMES[$i]}" | awk '{print $1}')"
    [ "$sha_arquivo" = "${MINIO_SHAS[$i]}" ] \
      || die "sha256 de ${MINIO_NAMES[$i]} difere do manifesto ($sha_arquivo != ${MINIO_SHAS[$i]})"
  done
fi

# SHA256SUMS definitivo: exige os tarballs, que são copiados para backend/dist
ETAPA="checksums"
info "Gerando SHA256SUMS"
run uv run --project backend python scripts/build_release.py --checksums-only
if [ "$DRY_RUN" -eq 0 ]; then
  [ -f "$SUMS_PATH" ] || die "artefato esperado não encontrado: $SUMS_PATH"
  for asset in "${MINIO_ASSETS[@]}"; do
    [ -f "$asset" ] || die "tarball esperado não encontrado: $asset"
    grep -q "  $(basename "$asset")\$" "$SUMS_PATH" || die "$SUMS_PATH não lista $(basename "$asset")"
  done
fi

# Criação da release e envio dos assets num passo só: não há estado "release sem os binários"
N_ASSETS=$((4 + ${#MINIO_ASSETS[@]}))
CMD_RELEASE=(gh release create "$TAG" "$WHEEL_PATH" "$CONSTRAINTS_PATH"
  "${MINIO_ASSETS[@]}" "$SUMS_PATH" "$INSTALL_SH"
  --repo "$REPO_SLUG" --title "$TAG" --notes-file "$NOTES_FILE" --verify-tag)

# Push e release
ETAPA="push/release"
info "Publicando commit, tag e release"
run git push --atomic origin main "$TAG"
PUSH_FEITO=1
run "${CMD_RELEASE[@]}"

ETAPA="concluído"
echo
if [ "$DRY_RUN" -eq 1 ]; then info "Dry-run de $TAG concluído (nada foi alterado)"; else info "Release $TAG concluída"; fi
echo "  release: https://github.com/$REPO_SLUG/releases/tag/$TAG"
echo "Para instalar/atualizar:"
echo "  curl -LsSf https://github.com/$REPO_SLUG/releases/download/$TAG/install.sh | sh"
echo "  curl -LsSf https://github.com/$REPO_SLUG/releases/latest/download/install.sh | sh   # última release"
