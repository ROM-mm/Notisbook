#!/usr/bin/env bash
# Abre o Notisbook com um comando: prepara o frontend se preciso e sobe o backend.
# Argumentos (--port, --root, --no-browser) são repassados ao `notisbook`.
# --replace é consumido aqui (não vai ao `notisbook`): encerra a instância registrada
# (`notisbook --stop-running`, de qualquer versão) antes de subir; se falhar, aborta.
# Sem --replace, o backend decide: troca uma instância de outra versão e recusa a mesma.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT_DIR/frontend"
PORT=8765

REPLACE=0
args=()
for a in "$@"; do
  if [[ "$a" == "--replace" ]]; then REPLACE=1; else args+=("$a"); fi
done
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    --port) PORT="${args[i + 1]:-$PORT}" ;;
    --port=*) PORT="${args[i]#--port=}" ;;
  esac
done

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Erro: '$1' não encontrado. $2" >&2; exit 1; }
}
need uv "Instale em https://docs.astral.sh/uv/"
need node "Instale o Node.js (https://nodejs.org/)."
need npm "Instale o Node.js (https://nodejs.org/)."

if [[ "$REPLACE" -eq 1 ]]; then
  uv run --project "$ROOT_DIR/backend" notisbook --stop-running \
    || { echo "Erro: não foi possível encerrar a instância em execução (--replace)." >&2; exit 1; }
fi

# Porta ocupada por um Notisbook segue adiante: o backend troca a versão ou recusa a mesma.
if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  if ! curl -sSI --max-time 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -qi '^x-notisbook:'; then
    echo "Erro: a porta $PORT está ocupada por outro processo. Use --port <outra>." >&2
    exit 1
  fi
fi

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  npm --prefix "$FRONTEND" ci
fi

INDEX="$FRONTEND/dist/index.html"
needs_build=0
if [[ ! -f "$INDEX" ]]; then
  needs_build=1
elif [[ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" "$FRONTEND/package.json" \
    "$FRONTEND/vite.config.ts" -newer "$INDEX" -print -quit)" ]]; then
  needs_build=1
fi
if [[ "$needs_build" -eq 1 ]]; then
  npm --prefix "$FRONTEND" run build
fi

# O backend aceita um diretório e escolhe o tarball da arquitetura pelo manifesto; o valor do operador prevalece.
if [[ -z "${NOTISBOOK_MINIO_DIST:-}" && -d "$ROOT_DIR/backend/dist/notislake" ]]; then
  export NOTISBOOK_MINIO_DIST="$ROOT_DIR/backend/dist/notislake"
fi

# O argparse aceita prefixos não ambíguos de opções longas (`--ro X`, `--roo=X`); `$1` é o argumento sem `=valor`,
# `$2` a opção completa e `$3` o mínimo de caracteres que a torna não ambígua.
is_long_option() {
  [[ "${#1}" -ge "$3" && "$2" == "$1"* ]]
}

# Opções longas da CLI que não pulam o seed (as que pulam estão no laço abaixo); com elas, decide se `--x` é
# desconhecida. `--if-missing` e `--yes` ficam de fora: só valem com `--seed-samples`/`uninstall`, que já pulam.
# Mínimos = menor prefixo não ambíguo no argparse.
is_known_passthrough_option() {
  is_long_option "$1" --port 3 || is_long_option "$1" --no-browser 3
}

# Primeira vez (pasta de notebooks ativa inexistente): copia os exemplos. Não semeia com --root do operador
# (a pasta é dele) nem quando o app não sobe ou o comando é de manutenção: -h/--help, --version, --stop-running,
# --check-notislake, --runtimes-summary, --install-default-runtimes, --seed-samples e os subcomandos `update`/`uninstall`
# (só o primeiro posicional; o valor de --port não conta) e opção `--*` desconhecida (o argparse vai falhar).
# Falha só avisa; o app sobe mesmo assim.
skip_seed=0
expect_value=0
seen_positional=0
for a in ${args[@]+"${args[@]}"}; do
  if [[ "$expect_value" -eq 1 ]]; then expect_value=0; continue; fi
  if [[ "$a" == -* ]]; then
    [[ "$a" == --* ]] && name="${a%%=*}" || name="$a"
    if [[ "$name" == "-h" ]] || is_long_option "$name" --help 3 || is_long_option "$name" --version 3 \
      || is_long_option "$name" --stop-running 4 || is_long_option "$name" --root 4 \
      || is_long_option "$name" --check-notislake 3 || is_long_option "$name" --runtimes-summary 4 \
      || is_long_option "$name" --install-default-runtimes 4 || is_long_option "$name" --seed-samples 4; then
      skip_seed=1
    elif [[ "$name" == --* && "$name" != "--" ]] && ! is_known_passthrough_option "$name"; then
      skip_seed=1
    fi
    if [[ "$a" != *=* ]] && is_long_option "$name" --port 3; then expect_value=1; fi
  elif [[ "$seen_positional" -eq 0 ]]; then
    seen_positional=1
    [[ "$a" == update || "$a" == uninstall ]] && skip_seed=1
  fi
done
if [[ "$skip_seed" -eq 0 ]]; then
  # O app repete o aviso de pasta salva recusada ao subir; o seed o suprime para sair uma vez só.
  NOTISBOOK_SEED_QUIET_ROOT_WARNING=1 uv run --project "$ROOT_DIR/backend" notisbook --seed-samples --if-missing </dev/null || {
    rc=$?
    # 130 = Ctrl+C durante a cópia: o operador desistiu, então não abre o app.
    [[ "$rc" -eq 130 ]] && exit 130
    echo "Aviso: não foi possível copiar os notebooks de exemplo; seguindo sem eles." >&2
  }
fi

exec uv run --project "$ROOT_DIR/backend" notisbook ${args[@]+"${args[@]}"}
