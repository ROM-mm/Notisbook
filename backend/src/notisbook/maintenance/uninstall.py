"""`notisbook uninstall`: remove o software e preserva os dados do usuário.

Remove: container e kernelspecs desta pasta de dados, `envs/`, `run/`, `minio/{bin,logs,run}`, o pacote
MinIO e, por último, o próprio `uv tool`. Mantém `minio/data`, credenciais, `catalog.db`, warehouses,
preferências e notebooks. Cada passo é idempotente (ausente = ok); a remoção do tool é um `execv`
final porque o Python não sobrevive ao ambiente que o hospeda. As mensagens saem em inglês.
"""

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ..api import lifecycle
from ..config import default_home
from ..notislake import binary
from ..notislake.supervisor import LockBusyError, acquire_flock, lock_path
from ..runtimes.docker import catalog as docker_catalog
from ..runtimes.docker import cli as docker_cli
from ..runtimes.docker import kernelspec as docker_kernelspec
from ..runtimes.docker.service import ContainerInfo, inspect_container
from ..runtimes.duckdb import kernelspec as duckdb_kernelspec
from ..spark import kernelspec as spark_kernelspec
from ..spark.bundles import SAFETY_WAREHOUSE_DIR, WAREHOUSE_DIR
from . import toolenv

CONFIRM_WORD = "uninstall"
DOCKER_STOP_GRACE_S = 10
DOCKER_TIMEOUT_S = 60.0
LEGACY_ENV_GLOB = f"{spark_kernelspec.LEGACY_PREFIX}*"
# Presença de qualquer um prova que a pasta é uma home do Notisbook (pastas como `envs/` e `run/` são genéricas).
HOME_MARKERS = ("catalog.db", "preferences.json", "minio/credentials.json", "notislake-connection.json")
# Guarda o flock do backend; só pode sumir depois de o lock ser liberado.
RUN_LOCK_DIR = "run"
# Dados que nunca são tocados (relativos à pasta de dados), só listados para o operador.
KEEP_NAMES = (
    "minio/data",
    "minio/credentials.json",
    "catalog.db",
    "catalog.db-wal",
    "catalog.db-shm",
    WAREHOUSE_DIR,
    SAFETY_WAREHOUSE_DIR,
    "preferences.json",
    "notebooks",
    "notislake-connection.json",
)


@dataclass(frozen=True)
class _Item:
    label: str
    size: int | None = None


def _path_size(path: Path) -> int:
    """Soma dos bytes sob `path` sem seguir links simbólicos."""
    try:
        if path.is_symlink() or path.is_file():
            return path.lstat().st_size
    except OSError:
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _home_skip_reason(home: Path) -> str | None:
    """Por que as pastas de software de `home` não podem ser removidas; None = é uma home do Notisbook."""
    try:
        resolved, user_home = home.resolve(), Path.home().resolve()
    except (OSError, RuntimeError):
        return "cannot resolve the data folder"
    if resolved == user_home or resolved in user_home.parents:
        return "it is your home folder or one of its parents"
    if not any((home / marker).exists() for marker in HOME_MARKERS):
        return "it does not look like a Notisbook data folder"
    return None


def _remove_paths(home: Path) -> list[Path]:
    """Pastas de software desta home que existem agora (a ordem é a da remoção); vazio se `home` não for validada."""
    if _home_skip_reason(home) is not None:
        return []
    minio = home / "minio"
    candidates = [home / spark_kernelspec.ENVS_DIR, *sorted(home.glob(LEGACY_ENV_GLOB)), minio / "bin", minio / "logs"]
    candidates += [home / lifecycle.RUN_DIR, minio / RUN_LOCK_DIR]
    return [p for p in candidates if p.exists() or p.is_symlink()]


def _dist_dir() -> Path | None:
    """Pacote MinIO padrão; nunca `NOTISBOOK_MINIO_DIST`, que é do operador."""
    dist = binary.default_dist_dir()
    if dist.name != "notislake" or dist.parent.name != "notisbook":
        return None
    return dist if dist.exists() or dist.is_symlink() else None


def _rm(path: Path) -> None:
    """Remove arquivo, link ou pasta; ausente é ok. Nunca segue links."""
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _same_path(a: str, b: Path) -> bool:
    try:
        return str(Path(a).resolve()).casefold() == str(b.resolve()).casefold()
    except OSError:
        return False


def _mounted_from(info: ContainerInfo, home: Path) -> bool:
    """O container foi criado a partir desta pasta de dados: monta o `warehouse/` dela."""
    return any(_same_path(mount, home / WAREHOUSE_DIR) for mount in info.mounts)


def _assess_container(home: Path) -> str:
    """`ours` | `absent` | `foreign` | `other_home` | `unavailable`; só leitura."""
    runtime = docker_catalog.CATALOG[0]
    try:
        if docker_cli.docker_binary() is None or not docker_cli.is_available():
            return "unavailable"
        info = inspect_container(runtime)
    except docker_cli.DockerError:
        return "unavailable"
    if info is None:
        return "absent"
    if not info.owned_by(runtime):
        return "foreign"
    return "ours" if _mounted_from(info, home) else "other_home"


def _remove_container(home: Path) -> str | None:
    """Para e remove o container desta pasta. Devolve o estado avaliado; `DockerError` se o docker falhar."""
    state = _assess_container(home)
    if state != "ours":
        return state
    name = docker_catalog.CATALOG[0].container
    docker_cli.run(["stop", "-t", str(DOCKER_STOP_GRACE_S), name], timeout=DOCKER_TIMEOUT_S)
    result = docker_cli.run(["rm", "-f", name], timeout=DOCKER_TIMEOUT_S)
    if result.returncode != 0:
        raise docker_cli.DockerError("docker rm: could not remove the container")
    return state


def _docker_spec_is_ours() -> bool:
    """O kernelspec Docker aponta para o Python deste ambiente (que está prestes a sumir)."""
    runtime = docker_catalog.CATALOG[0]
    if docker_kernelspec.read_registration(runtime) is None:
        return False
    try:
        spec = json.loads((docker_kernelspec.kernelspec_dir(runtime) / "kernel.json").read_text(encoding="utf-8"))
        python = Path(os.path.abspath(spec["argv"][0]))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False
    return python.is_relative_to(Path(sys.prefix).absolute())


def _kernel_names(home: Path) -> list[str]:
    names = [entry.kernel_name for entry in spark_kernelspec.discover(home)]
    if duckdb_kernelspec.discover(home) is not None:
        names.append(duckdb_kernelspec.KERNEL_NAME)
    return names


def _container_line(state: str) -> str:
    runtime = docker_catalog.CATALOG[0]
    return {
        "ours": f"Docker container {runtime.container} (stop and remove)",
        "absent": f"Docker container {runtime.container} (not present)",
        "foreign": f"Docker container {runtime.container} (not created by Notisbook; left alone)",
        "other_home": f"Docker container {runtime.container} (belongs to another data folder; left alone)",
        "unavailable": f"Docker container {runtime.container} (Docker is unavailable; not checked)",
    }[state]


def _print_inventory(home: Path, env: toolenv.ToolEnv, container: str) -> None:
    remove = [_Item(f"uv tool 'notisbook' {env.version}" if env.managed else "uv tool 'notisbook' (not installed as a uv tool; skipped)")]
    dist = _dist_dir()
    if dist is not None:
        remove.append(_Item(f"MinIO package {dist}", _path_size(dist)))
    remove += [_Item(str(p), _path_size(p)) for p in _remove_paths(home)]
    remove += [_Item(f"Jupyter kernel '{name}'") for name in _kernel_names(home)]
    remove.append(_Item(_container_line(container)))
    print("Notisbook will REMOVE:")
    for item in remove:
        print(f"  - {item.label}" + (f" ({_human(item.size)})" if item.size is not None else ""))
    print(f"\nNotisbook will KEEP (data folder {home}):")
    kept = [(name, home / name) for name in KEEP_NAMES if (home / name).exists()]
    for name, path in kept or [("(nothing found)", home)]:
        print(f"  - {name}" + (f" ({_human(_path_size(path))})" if kept else ""))
    print("  - Docker images and any .ipynb outside the data folder\n")


def _confirmed(assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Notisbook: refusing to uninstall without confirmation; stdin is not a terminal (use --yes).", file=sys.stderr)
        return False
    try:
        answer = input(f"Type '{CONFIRM_WORD}' to continue: ")
    except EOFError:
        answer = ""
    if answer.strip() != CONFIRM_WORD:
        print("Notisbook: aborted; nothing was removed.", file=sys.stderr)
        return False
    return True


def _clean_container(home: Path, failures: list[str]) -> None:
    runtime = docker_catalog.CATALOG[0]
    try:
        state = _remove_container(home)
    except docker_cli.DockerError as exc:
        failures.append(str(exc))
        return
    if state == "unavailable":
        print(
            f"Notisbook: Docker is unavailable; container {runtime.container} was not checked. If it exists and is yours, "
            f"remove it later with: docker rm -f {runtime.container}",
            file=sys.stderr,
        )
    elif state == "ours":
        print(f"Removed container {runtime.container}.")
    # Sem container nosso por perto, só o kernelspec que aponta para este ambiente é do app.
    if state in ("ours", "absent") and (state == "ours" or _docker_spec_is_ours()):
        try:
            docker_kernelspec.remove_kernelspec(runtime)
        except OSError as exc:
            failures.append(f"{docker_kernelspec.kernelspec_dir(runtime)}: {exc.strerror}")


def _clean_kernels(home: Path, failures: list[str]) -> None:
    try:
        for entry in spark_kernelspec.discover(home):
            spark_kernelspec.remove_kernelspec(entry.kernel_name)
        if duckdb_kernelspec.discover(home) is not None:
            duckdb_kernelspec.remove_kernelspec()
    except OSError as exc:
        failures.append(f"Jupyter kernels: {exc.strerror}")


def _clean_paths(paths: list[Path], failures: list[str]) -> None:
    for path in paths:
        try:
            _rm(path)
        except OSError as exc:
            failures.append(f"{path}: {exc.strerror}")


def _clean_dist(failures: list[str]) -> None:
    dist = _dist_dir()
    if dist is None:
        return
    try:
        _rm(dist)
        try:
            dist.parent.rmdir()  # só some se ficou vazio
        except OSError:
            pass
    except OSError as exc:
        failures.append(f"{dist}: {exc.strerror}")


def _clean_home(home: Path) -> list[str]:
    failures: list[str] = []
    _clean_container(home, failures)
    _clean_kernels(home, failures)
    reason = _home_skip_reason(home)
    if reason is not None:
        print(f"Notisbook: skipped removing folders inside {home}: {reason}.", file=sys.stderr)
    lock_dir = home / "minio" / RUN_LOCK_DIR
    _clean_paths([p for p in _remove_paths(home) if p != lock_dir], failures)
    _clean_dist(failures)
    return failures


def _take_lock(home: Path) -> int | None:
    """Toma o flock do backend sem bloquear; None se a pasta ainda não tem `minio/run` (nada a travar)."""
    try:
        return acquire_flock(lock_path(home))
    except FileNotFoundError:
        return None


def run(*, assume_yes: bool) -> int:
    """Executa o uninstall; devolve o exit code (em sucesso com o tool, o `execv` substitui o processo)."""
    home = default_home()
    env = toolenv.detect()
    if env.orphaned:
        print("Notisbook: `uv` was not found in PATH, so the tool cannot be removed. Install or expose uv and retry.", file=sys.stderr)
        return 1
    _print_inventory(home, env, _assess_container(home))
    if not _confirmed(assume_yes):
        return 1
    try:
        lifecycle.stop_running_instance(home)
    except lifecycle.PreviousInstanceError as exc:
        print(f"Notisbook: {exc}", file=sys.stderr)
        return 1
    try:
        lock_fd = _take_lock(home)
    except LockBusyError:
        print(f"Notisbook: another Notisbook is using the data folder {home}; close it and retry.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Notisbook: cannot check the lock in {home} ({exc.strerror}).", file=sys.stderr)
        return 1
    failures = _clean_home(home)
    if lock_fd is not None:
        os.close(lock_fd)
    _clean_paths([p for p in _remove_paths(home) if p == home / "minio" / RUN_LOCK_DIR], failures)
    if failures:
        print("Notisbook: some items could not be removed; the tool was kept so you can retry:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return _finish(env)


def _finish(env: toolenv.ToolEnv) -> int:
    if not env.managed or env.uv is None:
        print("Notisbook: not running from a uv tool install, so the tool itself was not removed. Data was kept.")
        return 0
    print("Removing the notisbook tool with uv; your data was kept.")
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execv(env.uv, ["uv", "tool", "uninstall", toolenv.TOOL_NAME])
    except OSError as exc:
        print(f"Notisbook: could not run uv ({exc.strerror}); run: uv tool uninstall {toolenv.TOOL_NAME}", file=sys.stderr)
        return 1
    return 0
