"""Apaga resíduos de build e release do Notisbook (somente biblioteca padrão).

Uso: python3 scripts/clean.py [--deep] [--skip-uv] [--yes] [--dry-run]
Padrão: remove o que é regenerável e barato (frontend/dist, _frontend/, caches,
__pycache__, tarballs do MinIO copiados e artefatos de versões antigas em
backend/dist). `--deep` soma o regenerável caro (node_modules, backend/.venv) e a etapa
`uv cache clean`, que apaga o cache inteiro do uv (global: o próximo `uv run`/`./start.sh`
baixa tudo de novo).
backend/dist/notislake (fonte dos tarballs MinIO) é protegido: nunca é alvo.
Sempre lista alvos e tamanhos antes de apagar. Caminhos rastreados pelo git, ou
que contenham arquivos rastreados, nunca são tocados. Nunca usa `git clean`.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DIST = BACKEND / "dist"

# Áreas do operador: fora do alcance do script, inclusive na busca de __pycache__.
# Em PROTECTED_TOP, `.venv` é só o da raiz (1º componente); backend/.venv segue alvo do --deep.
# Em WALK_SKIP os nomes valem em qualquer profundidade: o walk não desce em nenhum `.venv`.
PROTECTED_TOP = frozenset({".git", ".claude", ".idea", ".venv", "docs", "todo", "site"})
# Protegido em qualquer modo: nem o caminho, nem o que está dentro, nem os pais dele viram alvo.
PROTECTED_PATHS = (("backend", "dist", "notislake"),)
WALK_SKIP = PROTECTED_TOP | {".venv", "venv", "node_modules"}
UV_TIMEOUT = 15
DU_TIMEOUT = 30
CACHE_DIRS = (".mypy_cache", ".ruff_cache", ".pytest_cache")

VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
PACKAGE_RE = re.compile(r"^notisbook-([^-]+)(?:-.+\.whl|\.tar\.gz)$")
CONSTRAINTS_RE = re.compile(r"^constraints-(.+)\.txt$")
NOTES_RE = re.compile(r"^release-notes-v(.+)\.md$")
MINIO_TARBALL_RE = re.compile(r"^notislake-minio-.+\.tar\.gz$")


class CleanError(RuntimeError):
    """Falha que impede o script de continuar com segurança."""


@dataclass
class Target:
    label: str
    size: int = 0
    paths: list[Path] = field(default_factory=list)

    def remove(self) -> None:
        delete_paths(self.paths)


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def tree_size(path: Path) -> int:
    """Uso em disco sem seguir symlinks; hardlinks contados uma vez (como o `du`)."""
    seen: set[tuple[int, int]] = set()
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            st = current.lstat()
            if st.st_nlink > 1 and not stat.S_ISDIR(st.st_mode):
                if (st.st_dev, st.st_ino) in seen:
                    continue
                seen.add((st.st_dev, st.st_ino))
            total += st.st_blocks * 512
            if stat.S_ISDIR(st.st_mode):
                with os.scandir(current) as it:
                    stack.extend(Path(entry.path) for entry in it)
        except OSError:
            continue
    return total


def read_version() -> str:
    try:
        text = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CleanError("backend/pyproject.toml não encontrado") from exc
    match = VERSION_RE.search(text)
    if match is None:
        raise CleanError("versão não encontrada em backend/pyproject.toml")
    return match.group(1)


def tracked_paths() -> tuple[set[str], set[str]]:
    """Arquivos rastreados e seus diretórios-pai, relativos à raiz (posix)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CleanError("não foi possível listar os arquivos rastreados (git ls-files)") from exc
    files = {name for name in out.decode("utf-8", "surrogateescape").split("\0") if name}
    dirs = {parent for name in files for parent in Path(name).parents if str(parent) != "."}
    return files, {d.as_posix() for d in dirs}


def is_tracked(path: Path, tracked: tuple[set[str], set[str]]) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return rel in tracked[0] or rel in tracked[1]


def fold(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Partes sem distinção de caixa: no APFS `Notislake` e `notislake` são o mesmo diretório."""
    return tuple(part.casefold() for part in parts)


def is_inside_protected(parts: tuple[str, ...]) -> bool:
    """True se `parts` (relativo à raiz) é um caminho protegido ou está dentro dele."""
    folded = fold(parts)
    return any(folded[: len(prot)] == fold(prot) for prot in PROTECTED_PATHS)


def is_protected_path(parts: tuple[str, ...]) -> bool:
    """Como `is_inside_protected`, mas também True para os pais (evita rmtree num ancestral)."""
    folded = fold(parts)
    return is_inside_protected(parts) or any(fold(prot)[: len(folded)] == folded for prot in PROTECTED_PATHS)


def is_allowed(path: Path) -> bool:
    """Dentro do repo, fora das áreas protegidas e sem symlink nos diretórios-pai.

    O próprio `path` pode ser um symlink (só o link é removido); o que não pode é
    um componente intermediário apontar para fora, pois o rmtree o seguiria.
    """
    try:
        parts = path.relative_to(ROOT).parts
        parent = path.parent.resolve()
        resolved_parts = (*parent.relative_to(ROOT).parts, path.name)
    except (ValueError, OSError, RuntimeError):
        return False
    if not parts or resolved_parts[0].casefold() in PROTECTED_TOP or parts[0].casefold() in PROTECTED_TOP:
        return False
    if is_protected_path(parts) or is_protected_path(resolved_parts):
        return False
    return not any((ROOT.joinpath(*parts[:i])).is_symlink() for i in range(1, len(parts)))


def delete_paths(paths: list[Path]) -> None:
    for path in paths:
        if not is_allowed(path):
            raise CleanError(f"caminho fora do escopo permitido: {path}")
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif os.path.lexists(path):
            path.unlink()


def find_pycache() -> list[Path]:
    found: list[Path] = []
    for current, dirs, _files in os.walk(ROOT):
        if "__pycache__" in dirs:
            found.append(Path(current) / "__pycache__")
        rel = Path(current).relative_to(ROOT).parts
        dirs[:] = [
            d for d in dirs
            if d.casefold() not in WALK_SKIP and d != "__pycache__" and not is_inside_protected((*rel, d))
        ]
    return sorted(found)


def version_key(text: str) -> tuple[int, ...] | None:
    """Tupla numérica sem zeros finais (0.7 == 0.7.0); None se não for X.Y.Z numérica."""
    if not re.fullmatch(r"\d+(?:\.\d+)*", text):
        return None
    nums = [int(part) for part in text.split(".")]
    while nums and nums[-1] == 0:
        nums.pop()
    return tuple(nums)


def stale_dist_files(version: str) -> list[Path]:
    """Cópias dos tarballs do MinIO e artefatos de versão menor que a atual.

    Versão ≥ atual (release em preparo) ou não parseável é preservada.
    """
    if not DIST.is_dir():
        return []
    current = version_key(version)
    if current is None:
        print(f"aviso: versão {version!r} não numérica; artefatos versionados preservados.", file=sys.stderr)
    found: list[Path] = []
    entries = sorted(DIST.iterdir())
    # SHA256SUMS acompanha a release mais recente: só é obsoleto se não há wheel ≥ atual.
    has_current = current is None or any(
        entry.name.endswith(".whl")
        and (m := PACKAGE_RE.match(entry.name)) is not None
        and (key := version_key(m.group(1))) is not None
        and key >= current
        for entry in entries
    )
    for entry in entries:
        if not entry.is_file():
            continue
        # Sem backend/dist/notislake a cópia do tarball MinIO é a única: não apagar.
        if MINIO_TARBALL_RE.match(entry.name):
            if (DIST / "notislake").is_dir():
                found.append(entry)
            continue
        for regex in (PACKAGE_RE, CONSTRAINTS_RE, NOTES_RE):
            match = regex.match(entry.name)
            if match:
                old = version_key(match.group(1))
                if current is not None and old is not None and old < current:
                    found.append(entry)
                break
        else:
            if entry.name == "SHA256SUMS" and not has_current:
                found.append(entry)
    return found


def path_target(label: str, paths: list[Path]) -> Target | None:
    existing = [p for p in paths if os.path.lexists(p)]
    if not existing:
        return None
    return Target(label, paths=existing)


def default_targets(version: str) -> list[Target]:
    groups: list[tuple[str, list[Path]]] = [
        ("backend/dist/minio (legado)", [DIST / "minio"]),
        ("backend/dist: tarballs MinIO copiados e artefatos de versões anteriores a " + version, stale_dist_files(version)),
        ("frontend/dist", [FRONTEND / "dist"]),
        ("backend/src/notisbook/_frontend", [BACKEND / "src" / "notisbook" / "_frontend"]),
        ("frontend/tsconfig.tsbuildinfo", [FRONTEND / "tsconfig.tsbuildinfo"]),
        ("frontend/node_modules/.vite-temp", [FRONTEND / "node_modules" / ".vite-temp"]),
        ("caches de lint/tipos/testes", [base / name for base in (ROOT, BACKEND) for name in CACHE_DIRS]),
        ("__pycache__", find_pycache()),
    ]
    return [t for label, paths in groups if (t := path_target(label, paths))]


def deep_path_targets() -> list[Target]:
    groups: list[tuple[str, list[Path]]] = [
        ("frontend/node_modules", [FRONTEND / "node_modules"]),
        ("backend/.venv", [BACKEND / ".venv"]),
    ]
    return [t for label, paths in groups if (t := path_target(label, paths))]


def run_command(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise CleanError(f"{cmd[0]} falhou com exit {result.returncode}")


def apply_policy(targets: list[Target], tracked: tuple[set[str], set[str]]) -> None:
    """Pula caminhos rastreados, descarta aninhados e calcula os tamanhos."""
    for target in targets:
        kept = []
        for path in target.paths:
            if not is_allowed(path):
                print(f"aviso: {path} fora do escopo permitido ou atrás de symlink; ignorado.", file=sys.stderr)
            elif is_tracked(path, tracked):
                print(f"aviso: {path.relative_to(ROOT)} é rastreado pelo git; ignorado.", file=sys.stderr)
            else:
                kept.append(path)
        target.paths = kept
    every = [p for t in targets for p in t.paths]
    for target in targets:
        target.paths = [p for p in target.paths if not any(o in p.parents for o in every)]
        target.size = sum(tree_size(p) for p in target.paths)
    targets[:] = [t for t in targets if t.paths]


def cache_size(cache: Path) -> tuple[int | None, bool]:
    """Tamanho via `du -sk` com timeout (o cache global do uv é grande).

    Retorna (bytes, aproximado). `du` com exit != 0 mas total impresso (ex.: subdiretório
    ilegível) vale como aproximado; sem total legível ou timeout, (None, False).
    """
    try:
        result = subprocess.run(["du", "-sk", str(cache)], capture_output=True, text=True, check=False, timeout=DU_TIMEOUT)
        return int(result.stdout.split()[0]) * 1024, result.returncode != 0
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None, False


def uv_target() -> tuple[str, int | None, bool] | None:
    if shutil.which("uv") is None:
        print("aviso: uv não encontrado; `uv cache clean` ignorado.", file=sys.stderr)
        return None
    try:
        result = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=False, timeout=UV_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        print("aviso: `uv cache dir` falhou ou excedeu o tempo; `uv cache clean` ignorado.", file=sys.stderr)
        return None
    cache = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None
    if cache is None or not cache.is_dir():
        print("aviso: cache do uv não localizado; `uv cache clean` ignorado.", file=sys.stderr)
        return None
    return str(cache), *cache_size(cache)


def confirm(question: str) -> bool:
    try:
        answer = input(f"{question} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes", "s", "sim"}


def print_list(targets: list[Target], uv: tuple[str, int | None, bool] | None) -> None:
    print("Alvos de limpeza:")
    total = 0
    for target in targets:
        count = f" ({len(target.paths)} itens)" if len(target.paths) > 1 else ""
        print(f"  {human(target.size):>10}  {target.label}{count}")
        for path in target.paths if len(target.paths) <= 6 else []:
            print(f"{'':>14}{path.relative_to(ROOT)}")
        total += target.size
    print(f"  {'-' * 10}\n  {human(total):>10}  total")
    if uv:
        size = ("≥ " if uv[2] else "") + human(uv[1]) if uv[1] is not None else "tamanho desconhecido"
        print(f"\nEtapa com confirmação própria: uv cache clean (cache em {uv[0]}, hoje {size}).")
        print("Apaga o cache inteiro, é global (afeta outros projetos) e o próximo `uv run`/`./start.sh` baixa tudo de novo.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apaga resíduos de build e release do Notisbook, sempre listando antes.",
        epilog=(
            "Com --deep, `uv cache clean` (apaga o cache inteiro e global do uv) tem pergunta própria; só roda sem perguntar "
            "quando --yes é passado junto com --deep. uv ausente é ignorado com aviso."
        ),
    )
    parser.add_argument("--deep", action="store_true", help="inclui o regenerável caro (node_modules, backend/.venv) e o `uv cache clean`")
    parser.add_argument("--skip-uv", action="store_true", help="com --deep, não oferece nem roda o `uv cache clean`")
    parser.add_argument("--yes", action="store_true", help="não pede confirmação")
    parser.add_argument("--dry-run", action="store_true", help="só lista; não apaga nem pergunta")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = read_version()
    tracked = tracked_paths()
    targets = default_targets(version)
    uv = None
    if args.deep:
        targets += deep_path_targets()
    apply_policy(targets, tracked)
    if args.deep and not args.skip_uv:
        uv = uv_target()

    print(f"Versão atual preservada: {version}\n")
    if not targets and not uv:
        print("Nada a limpar.")
        return 0
    print_list(targets, uv)
    if args.dry_run:
        print("\ndry-run: nada foi apagado.")
        return 0

    failures = 0
    if targets and (args.yes or confirm("\nApagar os itens acima?")):
        for target in targets:
            try:
                target.remove()
                print(f"removido: {target.label}")
            except (OSError, CleanError) as exc:
                failures += 1
                print(f"erro: {target.label}: {exc}", file=sys.stderr)
    elif targets:
        print("Nada foi apagado.")
    uv_question = (
        "\nPare o app (`./start.sh`/`uv run`) antes: o uv espera o lock do cache em uso. "
        "Rodar `uv cache clean` (apaga o cache global inteiro do uv; o próximo start baixa tudo de novo)?"
    )
    if uv and (args.yes or confirm(uv_question)):
        try:
            run_command(["uv", "cache", "clean"])
        except CleanError as exc:
            failures += 1
            print(f"erro: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CleanError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        sys.exit(1)
