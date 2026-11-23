"""Apaga resíduos de build e release do Notisbook (somente biblioteca padrão).

Uso: python3 scripts/clean.py [--deep] [--skip-uv] [--yes] [--dry-run]
Padrão: remove o que é regenerável e barato (frontend/dist, _frontend/, caches,
__pycache__, tarballs do MinIO copiados e artefatos de versões antigas em
backend/dist). `--deep` soma o regenerável caro (cache do Docker, imagens golang
órfãs, backend/dist/notislake, node_modules, .venv) e a etapa `uv cache prune`.
Sempre lista alvos e tamanhos antes de apagar. Caminhos rastreados pelo git, ou
que contenham arquivos rastreados, nunca são tocados. Nunca usa `git clean`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DIST = BACKEND / "dist"
BUILD_MINIO = ROOT / "scripts" / "build_minio.py"
DOCKER_TIMEOUT = 30
DOCKER_DF_TIMEOUT = 120  # `docker system df` é lento com muito cache

# Áreas do operador: fora do alcance do script, inclusive na busca de __pycache__.
PROTECTED_TOP = frozenset({".git", ".claude", ".idea", "docs", "todo", "site"})
WALK_SKIP = PROTECTED_TOP | {".venv", "venv", "node_modules"}
CACHE_DIRS = (".mypy_cache", ".ruff_cache", ".pytest_cache")

GO_IMAGE_RE = re.compile(r'^GO_IMAGE\s*=\s*"([^"]+)"', re.MULTILINE)
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
    detail: str = ""
    paths: list[Path] = field(default_factory=list)
    action: Callable[[], None] | None = None

    def remove(self) -> None:
        if self.action is not None:
            self.action()
        else:
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


def read_go_image() -> str | None:
    try:
        match = GO_IMAGE_RE.search(BUILD_MINIO.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


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
    if not parts or resolved_parts[0] in PROTECTED_TOP or parts[0] in PROTECTED_TOP:
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
        dirs[:] = [d for d in dirs if d not in WALK_SKIP and d != "__pycache__"]
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
        if MINIO_TARBALL_RE.match(entry.name):
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
        ("backend/dist/notislake (fonte dos tarballs MinIO)", [DIST / "notislake"]),
        ("frontend/node_modules", [FRONTEND / "node_modules"]),
        ("backend/.venv", [BACKEND / ".venv"]),
        (".venv (raiz)", [ROOT / ".venv"]),
    ]
    return [t for label, paths in groups if (t := path_target(label, paths))]


def docker_run(args: list[str], timeout: int = DOCKER_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=False)


def docker_warn(step: str, exc: Exception) -> None:
    print(f"aviso: {step} falhou ({type(exc).__name__}); etapa ignorada.", file=sys.stderr)


def docker_available() -> bool:
    if shutil.which("docker") is None:
        print("aviso: docker não encontrado; etapas do Docker ignoradas.", file=sys.stderr)
        return False
    try:
        ok = docker_run(["info"]).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    if not ok:
        print("aviso: daemon do Docker indisponível; etapas do Docker ignoradas.", file=sys.stderr)
    return ok


def run_command(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise CleanError(f"{cmd[0]} falhou com exit {result.returncode}")


def docker_cache_target() -> Target | None:
    try:
        result = docker_run(["system", "df", "--format", "{{json .}}"], timeout=DOCKER_DF_TIMEOUT)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            row = json.loads(line)
            if isinstance(row, dict) and row.get("Type") == "Build Cache" and int(row.get("TotalCount", "0")) > 0:
                return Target(
                    "Docker build cache da máquina inteira (docker builder prune -a)",
                    detail=f"{row['TotalCount']} entradas, {row.get('Size', '?')} no cache",
                    action=lambda: run_command(["docker", "builder", "prune", "-a", "-f"]),
                )
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        docker_warn("`docker system df`", exc)
    return None


def docker_golang_targets(keep: str | None) -> list[Target]:
    if keep is None:
        print("aviso: GO_IMAGE não encontrada em build_minio.py; imagens golang ignoradas.", file=sys.stderr)
        return []
    targets: list[Target] = []
    try:
        result = docker_run(["images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}"])
        if result.returncode != 0:
            return []
        rows = [line.split("\t") for line in result.stdout.splitlines() if line.count("\t") == 2]
        keep_ids = {r[2] for r in rows if f"{r[0]}:{r[1]}" == keep}
        for repo, tag, image_id in rows:
            ref = f"{repo}:{tag}"
            if repo != "golang" or tag == "<none>" or ref == keep:
                continue
            shared = image_id in keep_ids
            size = 0
            if not shared:
                inspect = docker_run(["image", "inspect", "--format", "{{.Size}}", ref])
                size = int(inspect.stdout.strip() or 0) if inspect.returncode == 0 else 0
            detail = f"só remove a tag; camadas compartilhadas com {keep}" if shared else ""
            targets.append(
                Target(
                    f"imagem Docker {ref}",
                    size,
                    detail,
                    action=lambda r=ref: run_command(["docker", "rmi", r]),
                )
            )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        docker_warn("listagem de imagens golang", exc)
        return []
    return targets


def apply_policy(targets: list[Target], tracked: tuple[set[str], set[str]]) -> None:
    """Pula caminhos rastreados, descarta aninhados e calcula os tamanhos."""
    for target in targets:
        kept = []
        for path in target.paths:
            if is_tracked(path, tracked):
                print(f"aviso: {path.relative_to(ROOT)} é rastreado pelo git; ignorado.", file=sys.stderr)
            elif is_allowed(path):
                kept.append(path)
            else:
                print(f"aviso: {path} fora do escopo permitido ou atrás de symlink; ignorado.", file=sys.stderr)
        target.paths = kept
    every = [p for t in targets for p in t.paths]
    for target in targets:
        target.paths = [p for p in target.paths if not any(o in p.parents for o in every)]
        target.size = sum(tree_size(p) for p in target.paths)
    targets[:] = [t for t in targets if t.paths]


def uv_target() -> tuple[str, int] | None:
    if shutil.which("uv") is None:
        print("aviso: uv não encontrado; `uv cache prune` ignorado.", file=sys.stderr)
        return None
    result = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=False)
    cache = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None
    if cache is None or not cache.is_dir():
        print("aviso: cache do uv não localizado; `uv cache prune` ignorado.", file=sys.stderr)
        return None
    return str(cache), tree_size(cache)


def confirm(question: str) -> bool:
    try:
        answer = input(f"{question} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes", "s", "sim"}


def print_list(targets: list[Target], uv: tuple[str, int] | None) -> None:
    print("Alvos de limpeza:")
    total = 0
    for target in targets:
        extra = f" — {target.detail}" if target.detail else ""
        count = f" ({len(target.paths)} itens)" if len(target.paths) > 1 else ""
        print(f"  {human(target.size):>10}  {target.label}{count}{extra}")
        for path in target.paths if len(target.paths) <= 6 else []:
            print(f"{'':>14}{path.relative_to(ROOT)}")
        total += target.size
    print(f"  {'-' * 10}\n  {human(total):>10}  total (sem o cache do Docker, cujo tamanho vem do daemon)")
    if uv:
        print(f"\nEtapa com confirmação própria: uv cache prune (cache em {uv[0]}, hoje {human(uv[1])};")
        print("o prune libera só entradas não usadas).")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apaga resíduos de build e release do Notisbook, sempre listando antes.",
        epilog=(
            "Com --deep, `uv cache prune` tem pergunta própria; só roda sem perguntar "
            "quando --yes é passado junto com --deep. Docker ou uv ausentes são ignorados com aviso."
        ),
    )
    parser.add_argument("--deep", action="store_true", help="inclui o regenerável caro (Docker, node_modules, .venv, notislake) e o uv cache prune")
    parser.add_argument("--skip-uv", action="store_true", help="com --deep, não oferece nem roda o `uv cache prune`")
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
    if args.deep:
        if docker_available():
            cache = docker_cache_target()
            targets += ([cache] if cache else []) + docker_golang_targets(read_go_image())
        if not args.skip_uv:
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
    else:
        print("Nada foi apagado.")
    if uv and (args.yes or confirm("\nRodar `uv cache prune` (cache global do uv)?")):
        try:
            run_command(["uv", "cache", "prune"])
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
