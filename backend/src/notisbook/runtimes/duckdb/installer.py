"""Ambiente DuckDB imutável por versão: `<base>/envs/duckdb-<versão>-<id>/` com duckdb, ipykernel e extensões offline.

Cada instalação cria um env novo, baixa as extensões do manifesto conferindo o sha256 do `.gz` e do
`.duckdb_extension`, valida o carregamento offline e só então troca o kernelspec `duckdb-<maj>-<min>-<patch>` e remove
o env anterior da MESMA versão; as demais versões instaladas não são tocadas. Qualquer falha apaga o env novo e
preserva o kernelspec anterior. Subprocessos usam lista de argumentos.
"""

import asyncio
import gzip
import hashlib
import http.client
import logging
import os
import re
import shutil
import threading
import urllib.request
import uuid
import zlib
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ...jobs import Job, JobRegistry
from ...spark.installer import (
    DOWNLOAD_CHUNK,
    DOWNLOAD_TIMEOUT,
    PYTHON_VERSION,
    SCRUBBED_ENV,
    InstallError,
    RemoveFailed,
    run_command,
)
from ...spark.kernelspec import ENVS_DIR, TRASH_PREFIX, kernels_dir
from .kernelspec import (
    ENV_PREFIX,
    KERNEL_NAME,
    InstalledRuntime,
    discover,
    extension_dir,
    is_removable_env,
    kernel_name,
    remove_kernelspec,
    write_kernelspec,
)
from .manifest import (
    Manifest,
    UnsupportedPlatform,
    load_manifest,
    platform_key,
)

log = logging.getLogger(__name__)

PHASES = ("prereqs", "python", "venv", "install", "extensions", "validate", "kernelspec", "cleanup")
# Tetos contra resposta anômala: o maior .gz do manifesto tem ~28 MB e o maior descompactado ~100 MB.
MAX_GZ_BYTES = 256 << 20
MAX_EXT_BYTES = 1 << 30
# extensions.duckdb.org responde 403 ao User-Agent padrão do urllib.
USER_AGENT = "notisbook"
# Roda no interpretador do env novo, antes de trocar o kernelspec, para pegar divergência de
# versão/plataforma e extensão que não carrega sem depender de rede (autoinstall/autoload off).
VALIDATE_SCRIPT = """
import sys
import duckdb
version, platform_key, directory = sys.argv[1:4]
if duckdb.__version__ != version:
    raise SystemExit(f"installed duckdb is {duckdb.__version__}, expected {version}")
con = duckdb.connect(":memory:")
con.execute("SET autoinstall_known_extensions = false")
con.execute("SET autoload_known_extensions = false")
con.execute("SET extension_directory = ?", [directory])
found = con.execute("PRAGMA platform").fetchone()[0]
if found != platform_key:
    raise SystemExit(f"duckdb platform is {found}, manifest has {platform_key}")
for name in sys.argv[4:]:
    con.execute(f"LOAD {name}")
    print(f"loaded {name}")
print("duckdb-validate-ok")
"""


class InstallInProgress(Exception):
    """Another mutating job (install or remove) holds the lock of this DuckDB version."""


class NotInstalled(Exception):
    """No installed DuckDB runtime with that version."""


class UnknownVersion(Exception):
    """The version is not in the extension manifest."""


class DuckDBInstaller:
    def __init__(
        self,
        base_dir: Path,
        jobs: JobRegistry,
        has_active_session: Callable[[str], bool] | None = None,
        manifests: dict[str, Manifest] | None = None,
    ) -> None:
        self.base_dir = Path(os.path.abspath(base_dir.expanduser()))
        self._jobs = jobs
        self._has_active_session = has_active_session or (lambda _name: False)
        self._manifests = manifests
        # kernel name -> (job id, kind); `remove` has no job (empty id).
        self._active: dict[str, tuple[str, str]] = {}
        self._downloads: dict[str, asyncio.Future[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        self._env["UV_LINK_MODE"] = "copy"

    def try_acquire(self, name: str, job_id: str, kind: str) -> bool:
        """Take the per-kernel lock shared by install and remove; False when it is held."""
        if name in self._active:
            return False
        self._active[name] = (job_id, kind)
        return True

    def release(self, name: str) -> None:
        self._active.pop(name, None)

    def is_mutating(self, name: str, kind: str | None = None) -> bool:
        """True while the lock of `name` is held (by a job of `kind`, when given)."""
        held = self._active.get(name)
        return held is not None and (kind is None or held[1] == kind)

    def active_jobs(self) -> dict[str, tuple[str, str]]:
        """Kernel name -> (job id, kind) for the install jobs in progress."""
        return {name: held for name, held in self._active.items() if held[1] != "remove"}

    def entries_of_all(self) -> list[InstalledRuntime]:
        """Every installed runtime, newest first (includes the legacy `duckdb` kernel)."""
        return discover(self.base_dir)

    def entries_of(self, version: str) -> list[InstalledRuntime]:
        """Installed runtimes of the version: its `duckdb-*` kernel and, from before multi-version, the legacy `duckdb`."""
        return [e for e in discover(self.base_dir) if e.version == version]

    def find(self, version: str) -> InstalledRuntime:
        entries = self.entries_of(version)
        if not entries:
            raise NotInstalled(version)
        return next((e for e in entries if e.kernel_name == kernel_name(version)), entries[0])

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Future[Any]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def manifests(self) -> dict[str, Manifest]:
        """Manifests by version, newest first; raises ManifestError when the file is unreadable."""
        return self._manifests if self._manifests is not None else load_manifest()

    def start(self, version: str) -> Job:
        """Register the job and run it in the background.

        Raises UnknownVersion (not in the manifest), ManifestError, or InstallInProgress when the
        kernel name of this version is locked.
        """
        manifest = self.manifests().get(version)
        if manifest is None:
            raise UnknownVersion(version)
        name = kernel_name(version)
        if self.is_mutating(name):
            raise InstallInProgress(version)
        job = self._jobs.create("duckdb-install", version)
        self.try_acquire(name, job.id, "duckdb-install")
        self._spawn(self._run(job, manifest, name))
        return job

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def remove(self, version: str) -> asyncio.Future[None]:
        """Drop the kernelspecs of the version synchronously, then delete its envs in a thread.

        Other versions are untouched. Raises NotInstalled / InstallInProgress / RemoveFailed (kernelspec)
        before any env is touched; the future raises RemoveFailed with whatever is left.
        """
        name = kernel_name(version)
        if self.is_mutating(name):
            raise InstallInProgress(version)
        entries = self.entries_of(version)
        if not entries:
            raise NotInstalled(version)
        for entry in entries:
            try:
                remove_kernelspec(entry.kernel_name)
            except OSError as exc:
                raise RemoveFailed([str(kernels_dir() / entry.kernel_name)]) from exc
        self.try_acquire(name, "", "remove")
        return self._spawn(self._remove_envs(name, version, {e.env_dir for e in entries}))

    async def _remove_envs(self, name: str, version: str, env_dirs: set[Path]) -> None:
        try:
            await asyncio.to_thread(self._delete_version_envs, version, env_dirs)
        finally:
            self.release(name)

    def _delete_version_envs(self, version: str, env_dirs: set[Path]) -> None:
        """Move each env of the version to `envs/.trash-*` and delete it; raise with whatever is left."""
        envs = self.base_dir / ENVS_DIR
        pattern = re.compile(rf"{re.escape(ENV_PREFIX)}{re.escape(version)}-[0-9a-f]{{8}}")
        targets = set(env_dirs)
        if envs.is_dir():
            targets |= {p for p in envs.iterdir() if pattern.fullmatch(p.name) and p.is_dir()}
        left: list[str] = []
        for target in sorted(targets):
            if not is_removable_env(self.base_dir, target):
                log.warning("refusing to delete %s: outside the managed locations", target)
                left.append(str(target))
                continue
            doomed = envs / f"{TRASH_PREFIX}{target.name}"
            try:
                if doomed.exists():
                    shutil.rmtree(doomed)
                os.rename(target, doomed)
            except FileNotFoundError:
                continue
            except OSError:
                log.warning("could not move %s to trash", target, exc_info=True)
                left.append(str(target))
                continue
            shutil.rmtree(doomed, ignore_errors=True)
            if doomed.exists():
                left.append(str(doomed))
        if left:
            raise RemoveFailed(left)

    def sweep_trash(self, version: str | None = None) -> None:
        """Delete `envs/.trash-duckdb-*` left by an interrupted removal; failures only warn.

        With `version`, sweeps only that version's leftovers (the caller holds its kernel lock).
        """
        envs = self.base_dir / ENVS_DIR
        if not envs.is_dir():
            return
        stem = f"{ENV_PREFIX}{version}-*" if version else f"{ENV_PREFIX}*"
        for old in envs.glob(f"{TRASH_PREFIX}{stem}"):
            if old.is_dir() and is_removable_env(self.base_dir, old):
                shutil.rmtree(old, ignore_errors=True)

    @staticmethod
    def _progress(phase: str) -> float:
        return PHASES.index(phase) / len(PHASES)

    async def _cmd(self, job: Job, phase: str, args: list[str]) -> list[str]:
        return await run_command(job, phase, args, self._env, self._progress(phase))

    async def _run(self, job: Job, manifest: Manifest, name: str) -> None:
        env_dir: Path | None = None
        cancel = threading.Event()
        try:
            await job.start()
            await asyncio.to_thread(lambda: self.sweep_trash(manifest.duckdb_version))
            key = self._platform(manifest)
            uv = shutil.which("uv")
            if uv is None:
                raise InstallError("uv not found; install it with: brew install uv")
            await job.emit("prereqs", f"uv {uv}; DuckDB {manifest.duckdb_version} on {key}", self._progress("prereqs"))
            await self._cmd(job, "python", [uv, "python", "install", PYTHON_VERSION])
            env_dir = self.base_dir / ENVS_DIR / f"{ENV_PREFIX}{manifest.duckdb_version}-{uuid.uuid4().hex[:8]}"
            env_dir.parent.mkdir(parents=True, exist_ok=True)
            await self._cmd(job, "venv", [uv, "venv", str(env_dir), "--python", PYTHON_VERSION])
            python = str(env_dir / "bin" / "python")
            await self._cmd(
                job, "install", [uv, "pip", "install", "--python", python, f"duckdb=={manifest.duckdb_version}", "ipykernel"]
            )
            await self._install_extensions(job, env_dir, manifest, key, cancel)
            await self._validate(job, python, env_dir, manifest, key)
            await job.emit("kernelspec", f"writing kernelspec {name}", self._progress("kernelspec"))
            current = await asyncio.to_thread(self.entries_of, manifest.duckdb_version)
            previous = {e.env_dir for e in current}
            await asyncio.to_thread(write_kernelspec, manifest.duckdb_version, env_dir, manifest.names)
            installed, env_dir = env_dir, None  # switched: the new env must survive from here on
            await self._supersede_legacy(job, current)
            await self._cleanup(job, manifest.duckdb_version, installed, previous, {e.kernel_name for e in current})
            await job.finish("succeeded")
        except asyncio.CancelledError:
            cancel.set()  # the download thread cannot be cancelled; it stops at the next chunk
            if (download := self._downloads.get(name)) is not None and not download.done():
                await asyncio.wait({download}, timeout=DOWNLOAD_TIMEOUT)
            await self._discard(env_dir)
            await job.finish("failed", "cancelled")
            raise
        except InstallError as exc:
            await self._discard(env_dir)
            await job.finish("failed", str(exc))
        except Exception:
            log.exception("unexpected failure installing DuckDB %s", manifest.duckdb_version)
            await self._discard(env_dir)
            await job.finish("failed", "unexpected error; see server log")
        finally:
            self.release(name)
            self._downloads.pop(name, None)

    @staticmethod
    def _platform(manifest: Manifest) -> str:
        try:
            key = platform_key()
        except UnsupportedPlatform as exc:
            raise InstallError(f"prereqs: no DuckDB extensions for {exc}") from exc
        if any(key not in plats for plats in manifest.extensions.values()):
            raise InstallError(f"prereqs: manifest has no extensions for {key}")
        return key

    async def _install_extensions(
        self, job: Job, env_dir: Path, manifest: Manifest, key: str, cancel: threading.Event
    ) -> None:
        progress = self._progress("extensions")
        target = extension_dir(env_dir) / f"v{manifest.duckdb_version}" / key
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
        for name in manifest.names:
            await job.emit("extensions", f"downloading {manifest.url(key, name)}", progress)
            # Shielded and tracked so a cancelled job can still wait for the thread to stop.
            download = asyncio.ensure_future(asyncio.to_thread(self._fetch_extension, manifest, key, name, target, cancel))
            self._downloads[kernel_name(manifest.duckdb_version)] = download
            try:
                await asyncio.shield(download)
            except (OSError, EOFError, zlib.error, http.client.HTTPException) as exc:
                raise InstallError(f"extensions: cannot install {name}: {exc}") from exc
            digests = manifest.digests(key, name)
            await job.emit("extensions", f"verified sha256 {digests.sha256_gz} {name}.duckdb_extension.gz", progress)
            await job.emit("extensions", f"verified sha256 {digests.sha256_ext} {name}.duckdb_extension", progress)

    @staticmethod
    def _fetch_extension(manifest: Manifest, key: str, name: str, target: Path, cancel: threading.Event) -> None:
        """Download the .gz, check its sha256, decompress, check the sha256 of the extension, then rename."""
        url = manifest.url(key, name)
        if urlparse(url).scheme != "https":
            raise InstallError(f"extensions: unsupported URL scheme in {url}")
        digests = manifest.digests(key, name)
        gz_part = target / f".{name}.duckdb_extension.gz.part"
        ext_part = target / f".{name}.duckdb_extension.part"
        try:
            gz_hash = hashlib.sha256()
            size = 0
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response, gz_part.open("wb") as out:
                while chunk := response.read(DOWNLOAD_CHUNK):
                    if cancel.is_set():
                        raise InstallError(f"extensions: download of {name} cancelled")
                    size += len(chunk)
                    if size > MAX_GZ_BYTES:
                        raise InstallError(f"extensions: {name} download exceeds {MAX_GZ_BYTES} bytes")
                    gz_hash.update(chunk)
                    out.write(chunk)
            if gz_hash.hexdigest() != digests.sha256_gz:
                raise InstallError(
                    f"extensions: sha256 mismatch for {name}.duckdb_extension.gz: "
                    f"expected {digests.sha256_gz}, got {gz_hash.hexdigest()}"
                )
            ext_hash = hashlib.sha256()
            size = 0
            with gzip.open(gz_part, "rb") as source, ext_part.open("wb") as out:
                while chunk := source.read(DOWNLOAD_CHUNK):
                    if cancel.is_set():
                        raise InstallError(f"extensions: install of {name} cancelled")
                    size += len(chunk)
                    if size > MAX_EXT_BYTES:
                        raise InstallError(f"extensions: {name} expands beyond {MAX_EXT_BYTES} bytes")
                    ext_hash.update(chunk)
                    out.write(chunk)
            if ext_hash.hexdigest() != digests.sha256_ext:
                raise InstallError(
                    f"extensions: sha256 mismatch for {name}.duckdb_extension: "
                    f"expected {digests.sha256_ext}, got {ext_hash.hexdigest()}"
                )
            os.replace(ext_part, target / f"{name}.duckdb_extension")
        finally:
            gz_part.unlink(missing_ok=True)
            ext_part.unlink(missing_ok=True)

    async def _validate(self, job: Job, python: str, env_dir: Path, manifest: Manifest, key: str) -> None:
        args = [python, "-I", "-c", VALIDATE_SCRIPT, manifest.duckdb_version, key, str(extension_dir(env_dir)), *manifest.names]
        lines = await self._cmd(job, "validate", args)
        if "duckdb-validate-ok" not in lines:
            raise InstallError("validate: extension load check did not complete")

    async def _supersede_legacy(self, job: Job, previous: list[InstalledRuntime]) -> None:
        """The legacy `duckdb` kernelspec of the same version is replaced by the versioned one."""
        for entry in previous:
            if entry.kernel_name == KERNEL_NAME:
                await job.emit("cleanup", f"replacing legacy kernelspec {KERNEL_NAME}", self._progress("cleanup"))
                try:
                    await asyncio.to_thread(remove_kernelspec, KERNEL_NAME)
                except OSError:
                    log.warning("could not remove the legacy kernelspec %s", KERNEL_NAME, exc_info=True)

    async def _cleanup(
        self, job: Job, version: str, installed: Path, previous: set[Path], kernel_names: set[str]
    ) -> None:
        """Remove superseded envs of this version only; failures only warn (the install already succeeded)."""
        envs = self.base_dir / ENVS_DIR
        stale = {p for p in envs.glob(f"{ENV_PREFIX}{version}-????????") if p.is_dir()} | previous
        # A session opened during the install runs on the old env (`previous`); keep only that one.
        in_use = any(self._has_active_session(n) for n in {kernel_name(version), *kernel_names})
        kept = (stale & previous) - {installed} if in_use else set()
        if kept:
            await job.emit(
                "cleanup",
                f"warning: kept {len(kept)} previous environment(s) in use by a kernel session; removing the other leftovers",
                self._progress("cleanup"),
            )
        for old in sorted(stale - {installed} - kept):
            await job.emit("cleanup", f"removing previous environment {old}", self._progress("cleanup"))
            await asyncio.to_thread(self._delete_env, old)

    def _delete_env(self, env_dir: Path) -> None:
        if not is_removable_env(self.base_dir, env_dir):
            log.warning("refusing to delete %s: outside the managed locations", env_dir)
            return
        try:
            shutil.rmtree(env_dir)
        except FileNotFoundError:
            pass
        except OSError:
            log.warning("could not delete %s", env_dir, exc_info=True)

    async def _discard(self, env_dir: Path | None) -> None:
        if env_dir is not None:
            await asyncio.to_thread(self._delete_env, env_dir)
