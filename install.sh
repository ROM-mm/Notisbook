#!/bin/sh
# Notisbook installer (macOS, Apple silicon).
#
#   curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh | sh
#
# Installs the Notisbook wheel with `uv tool` (Python 3.12, no source builds)
# and the bundled MinIO package into ~/.local/share/notisbook/notislake, after
# checking the SHA-256 of every downloaded file. Your data folder is never touched.
#
#   --version <X.Y.Z>   NOTISBOOK_VERSION       release to install (default: latest)
#   --uninstall                                 remove Notisbook; keeps your data (lake, catalog, notebooks, preferences)
#   -h, --help                                  show this help
#
# NOTISBOOK_INSTALL_FROM=<dir> reads the assets from a local folder (same file
# names as a release) instead of GitHub; used to test without a published release.
set -eu

REPO="ROM-mm/Notisbook"
UV_PINNED_VERSION="0.10.8"
UV_MIN_VERSION="0.8.4"
PYTHON_VERSION="3.12"

say() { printf '%s\n' "$*"; }
warn() { printf 'notisbook install: warning: %s\n' "$*" >&2; }
err() {
  printf 'notisbook install: %s\n' "$*" >&2
  exit 1
}
need() { command -v "$1" >/dev/null 2>&1 || err "needs \`$1\`; install it and retry"; }

usage() {
  cat <<'EOF'
Notisbook installer (macOS, Apple silicon).

  curl -LsSf https://github.com/ROM-mm/Notisbook/releases/latest/download/install.sh | sh

Installs the Notisbook wheel with `uv tool` (Python 3.12, no source builds)
and the bundled MinIO package into ~/.local/share/notisbook/notislake, after
checking the SHA-256 of every downloaded file. Your data folder is never touched.

  --version <X.Y.Z>   NOTISBOOK_VERSION       release to install (default: latest)
  --uninstall                                 remove Notisbook; keeps your data (lake, catalog, notebooks, preferences)
  -h, --help                                  show this help

NOTISBOOK_INSTALL_FROM=<dir> reads the assets from a local folder (same file
names as a release) instead of GitHub; used to test without a published release.
EOF
}

fetch() {
  # fetch <url-or-name> <dest>: HTTPS download, or a copy from NOTISBOOK_INSTALL_FROM.
  if [ -n "$install_from" ]; then
    [ -f "$install_from/$1" ] || return 1
    cp "$install_from/$1" "$2"
  elif command -v curl >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -fsSL --retry 3 -o "$2" "$base/$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$2" "$base/$1"
  else
    err "needs curl or wget"
  fi
}

latest_version() {
  # Follows the "latest" redirect; falls back to the API. No jq needed.
  url="https://github.com/$REPO/releases/latest"
  tag=""
  if command -v curl >/dev/null 2>&1; then
    tag="$(curl --proto '=https' --tlsv1.2 -fsSLI -o /dev/null -w '%{url_effective}' "$url" 2>/dev/null |
      sed -n 's|.*/releases/tag/v\([0-9][0-9.]*\)$|\1|p')" || tag=""
    if [ -z "$tag" ]; then
      tag="$(curl --proto '=https' --tlsv1.2 -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null |
        sed -n 's/.*"tag_name": *"v\([0-9][0-9.]*\)".*/\1/p' | head -n 1)" || tag=""
    fi
  elif command -v wget >/dev/null 2>&1; then
    tag="$(wget -q --max-redirect=5 -S -O /dev/null "$url" 2>&1 |
      sed -n 's|.*Location: .*/releases/tag/v\([0-9][0-9.]*\)\r*$|\1|p' | tail -n 1)" || tag=""
  else
    err "needs curl or wget"
  fi
  [ -n "$tag" ] || err "cannot determine the latest release; pass --version X.Y.Z"
  printf '%s\n' "$tag"
}

detect_arch() {
  [ "$(uname -s)" = "Darwin" ] || err "Notisbook supports macOS only"
  machine="$(uname -m)"
  # A shell running under Rosetta reports x86_64 on Apple silicon.
  if [ "$machine" = "x86_64" ] && [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = "1" ]; then
    machine="arm64"
  fi
  case "$machine" in
    arm64 | aarch64) echo "arm64" ;;
    x86_64) err "Notisbook supports Apple silicon only (detected x86_64)" ;;
    *) err "unsupported CPU architecture: $machine" ;;
  esac
}

# Prints the file names listed in SHA256SUMS that match the regex, one per line.
sums_names() {
  awk '{ n = $2; sub(/^\*/, "", n); print n }' "$2" | grep -E "$1" || true
}

uv_version_ok() {
  # uv_version_ok <found> <minimum>: true when found >= minimum (numeric X.Y.Z compare).
  awk -v a="$1" -v b="$2" 'BEGIN {
    na = split(a, x, "."); nb = split(b, y, ".")
    for (i = 1; i <= 3; i++) {
      xv = (i <= na) ? x[i] + 0 : 0; yv = (i <= nb) ? y[i] + 0 : 0
      if (xv > yv) exit 0
      if (xv < yv) exit 1
    }
    exit 0 }'
}

ensure_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    need curl
    say "Installing uv $UV_PINNED_VERSION..."
    uv_dir="${HOME:?HOME is not set}/.local/bin"
    curl --proto '=https' --tlsv1.2 -LsSf "https://astral.sh/uv/$UV_PINNED_VERSION/install.sh" |
      env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$uv_dir" sh >/dev/null ||
      err "could not install uv $UV_PINNED_VERSION"
    PATH="$uv_dir:$PATH"
    export PATH
  fi
  found="$(uv --version 2>/dev/null | awk '{print $2}')"
  [ -n "$found" ] || err "could not read the version of uv"
  uv_version_ok "$found" "$UV_MIN_VERSION" ||
    err "uv $found is too old; Notisbook needs uv $UV_MIN_VERSION or newer (run \`uv self update\`)"
}

# The directory where `uv tool` puts executables.
uv_bin_dir() { uv tool dir --bin 2>/dev/null || echo "${HOME}/.local/bin"; }

# The uv tool executable only: a notisbook found elsewhere in PATH is not ours.
notisbook_bin() {
  candidate="$(uv_bin_dir)/notisbook"
  if [ -x "$candidate" ]; then
    echo "$candidate"
  fi
}

dist_dir() {
  # A relative XDG_DATA_HOME is ignored, as in binary.py.
  case "${XDG_DATA_HOME:-}" in
    /*) data_home="$XDG_DATA_HOME" ;;
    *) data_home="${HOME:?HOME is not set}/.local/share" ;;
  esac
  echo "$data_home/notisbook/notislake"
}

warn_path() {
  bindir="$(uv_bin_dir)"
  case ":$PATH:" in
    *":$bindir:"*) return 0 ;;
  esac
  say ""
  say "$bindir is not in your PATH. Add it to your shell profile, for example:"
  say "  export PATH=\"$bindir:\$PATH\""
  say "or run: uv tool update-shell"
}

warn_brew() {
  brew_note=""
  command -v brew >/dev/null 2>&1 || return 0
  prefix="$(brew --prefix 2>/dev/null)" || return 0
  [ -n "$prefix" ] && [ -e "$prefix/bin/notisbook" ] || return 0
  warn "a Homebrew copy of notisbook exists at $prefix/bin/notisbook and may shadow this install."
  warn "remove it with: brew uninstall notisbook && brew untap rom-mm/tap"
  # Kept for the final block: the screen clear there would erase the warning above.
  brew_note="a Homebrew copy of notisbook exists at $prefix/bin/notisbook and may shadow this install; remove it with: brew uninstall notisbook && brew untap rom-mm/tap"
}

do_uninstall() {
  need uv
  bin="$(notisbook_bin)"
  # Versions that ship the `uninstall` command do the full cleanup; older ones fall back to the steps below.
  if [ -n "$bin" ] && "$bin" uninstall --help 2>&1 | grep -q -- '--yes'; then
    exec "$bin" uninstall --yes
  fi
  if [ -n "$bin" ]; then
    "$bin" --stop-running || err "could not stop the running Notisbook; stop it and retry"
  fi
  if uv tool list 2>/dev/null | grep -q '^notisbook '; then
    uv tool uninstall notisbook || err "uv could not uninstall notisbook"
  else
    say "notisbook is not installed as a uv tool."
  fi
  dist="$(dist_dir)"
  if [ -d "$dist" ]; then
    rm -rf "$dist"
    rmdir "$(dirname "$dist")" 2>/dev/null || true
    say "Removed $dist."
  fi
  say "Notisbook was uninstalled. Your data was kept in ${NOTISBOOK_HOME:-$HOME/.notisbook}."
  warn "the cleanup was partial: this version cannot remove the Spark/DuckDB environments (envs/), the Jupyter kernels or the Docker container."
  warn "for a full cleanup, reinstall the latest Notisbook, run \`notisbook uninstall\`, or delete those folders yourself."
}

do_install() {
  need uname
  need awk
  need shasum
  arch="$(detect_arch)"
  ensure_uv

  tmp="$(mktemp -d 2>/dev/null || mktemp -d -t notisbook)"
  trap 'rm -rf "$tmp"' EXIT INT TERM

  if [ -n "$install_from" ]; then
    [ -d "$install_from" ] || err "NOTISBOOK_INSTALL_FROM is not a directory: $install_from"
    base=""
    fetch SHA256SUMS "$tmp/SHA256SUMS" || err "SHA256SUMS not found in $install_from"
    if [ -z "$version" ]; then
      wheels="$(sums_names '^notisbook-[0-9][^-]*-py3-none-any\.whl$' "$tmp/SHA256SUMS")"
      [ -n "$wheels" ] || err "no notisbook wheel listed in $install_from/SHA256SUMS"
      [ "$(printf '%s\n' "$wheels" | wc -l)" -eq 1 ] || err "several wheels listed in SHA256SUMS; pass --version X.Y.Z"
      version="$(printf '%s\n' "$wheels" | sed -n 's/^notisbook-\([^-]*\)-py3-none-any\.whl$/\1/p')"
    fi
  else
    if [ -z "$version" ]; then
      version="$(latest_version)"
    fi
    base="https://github.com/$REPO/releases/download/v$version"
    say "Downloading Notisbook $version..."
    fetch SHA256SUMS "$tmp/SHA256SUMS" || err "cannot download SHA256SUMS for $version"
  fi

  wheel="notisbook-$version-py3-none-any.whl"
  constraints="constraints-$version.txt"
  minio="$(sums_names "^notislake-minio-.*-darwin-$arch\\.tar\\.gz\$" "$tmp/SHA256SUMS" | head -n 1)"
  [ -n "$minio" ] || err "SHA256SUMS lists no MinIO package for darwin-$arch"

  : >"$tmp/SHA256SUMS.selected"
  for name in "$wheel" "$constraints" "$minio"; do
    awk -v n="$name" '{ f = $2; sub(/^\*/, "", f); if (f == n) print }' "$tmp/SHA256SUMS" >>"$tmp/SHA256SUMS.selected"
    grep -q "[ *]$name\$" "$tmp/SHA256SUMS.selected" || err "$name is not listed in SHA256SUMS"
    fetch "$name" "$tmp/$name" || err "cannot get $name"
  done
  (cd "$tmp" && shasum -a 256 -c SHA256SUMS.selected >/dev/null 2>&1) ||
    err "checksum mismatch; the download is corrupt or was tampered with. Nothing was installed."

  warn_brew

  say "Stopping any running Notisbook..."
  uvx --from "$tmp/$wheel" -c "$tmp/$constraints" --python "$PYTHON_VERSION" --managed-python --no-build \
    notisbook --stop-running </dev/null || err "could not stop the running Notisbook; nothing was changed"

  # First install = no tool before this point and not launched by `notisbook update`; set before the tool exists.
  fresh=0
  if [ -z "$(notisbook_bin)" ] && [ -z "${NOTISBOOK_UPDATING:-}" ]; then
    fresh=1
  fi

  say "Installing Notisbook $version..."
  uv tool install --force --python "$PYTHON_VERSION" --managed-python --no-build \
    -c "$tmp/$constraints" "$tmp/$wheel" </dev/null || err "uv could not install the Notisbook wheel"

  dist="$(dist_dir)"
  mkdir -p "$dist"
  cp "$tmp/$minio" "$dist/.$minio.tmp"
  mv -f "$dist/.$minio.tmp" "$dist/$minio"
  for old in "$dist"/notislake-minio-*.tar.gz; do
    [ -e "$old" ] || continue
    [ "$old" = "$dist/$minio" ] || rm -f "$old"
  done

  bin="$(notisbook_bin)"
  [ -n "$bin" ] || err "the notisbook executable was not found after installing"
  env -u NOTISBOOK_MINIO_DIST "$bin" --check-notislake || err "the MinIO package check failed"

  runtimes_failed=0
  samples_failed=0
  runtimes_note=""
  if [ "$fresh" = 1 ]; then
    say "Installing default runtimes (may take several minutes)..."
    # A runtime failure must not fail the install (set -e): the user can add them in the app.
    if ! "$bin" --install-default-runtimes </dev/null; then
      runtimes_failed=1
      warn "could not install all default runtimes; install them in Settings › Runtimes"
    fi
    # --if-missing: an existing notebooks folder is never touched. A failure must not fail the install.
    if ! "$bin" --seed-samples --if-missing </dev/null; then
      samples_failed=1
      warn "could not copy the sample notebooks; the app still works without them"
    fi
  elif [ -z "${NOTISBOOK_UPDATING:-}" ]; then
    # Kept for the final block: the screen clear below would erase it.
    runtimes_note="Default runtimes are installed only on the first install; add them in Settings › Runtimes."
  fi

  # Clear only on a terminal and only when nothing failed: the runtime and samples warnings must stay on screen.
  if [ -t 1 ] && [ "$runtimes_failed" = 0 ] && [ "$samples_failed" = 0 ]; then
    # Home + erase display only: the scrollback must survive, so avoid the tool that also erases it.
    printf '\033[H\033[2J'
  fi

  say ""
  say "Notisbook $("$bin" --version 2>/dev/null || echo "$version") installed"
  say "  binary   $bin"
  say ""
  say "Runtimes"
  # A failed summary is cosmetic: warn and carry on.
  "$bin" --runtimes-summary </dev/null || warn "could not list the installed runtimes"
  [ -z "$runtimes_note" ] || say "  $runtimes_note"
  [ -z "$brew_note" ] || warn "$brew_note"
  warn_path
  say ""
  say "To start: notisbook"
}

main() {
  version="${NOTISBOOK_VERSION:-}"
  install_from="${NOTISBOOK_INSTALL_FROM:-}"
  uninstall=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --version)
        [ $# -ge 2 ] || err "--version needs a value"
        version="$2"
        shift 2
        ;;
      --uninstall)
        uninstall=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *) err "unknown option $1 (see --help)" ;;
    esac
  done
  version="${version#v}"
  case "$version" in
    *[!0-9A-Za-z.+-]*) err "invalid version: $version" ;;
  esac

  if [ "$uninstall" = "1" ]; then
    do_uninstall
  else
    do_install
  fi
}

main "$@"
