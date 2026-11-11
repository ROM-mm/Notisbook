#!/usr/bin/env bash
# Abre o Notisbook com um comando: prepara o frontend se preciso e sobe o backend.
# Argumentos (--port, --root, --no-browser) são repassados ao `notisbook`.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT_DIR/frontend"
PORT=8765

args=("$@")
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

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  if curl -sSI --max-time 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -qi '^x-notisbook:'; then
    echo "Notisbook já está rodando na porta $PORT. Nada foi alterado." >&2
  else
    echo "Erro: a porta $PORT está ocupada por outro processo. Use --port <outra>." >&2
  fi
  exit 1
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

exec uv run --project "$ROOT_DIR/backend" notisbook "$@"
