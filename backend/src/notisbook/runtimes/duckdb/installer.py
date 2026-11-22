"""Ambiente DuckDB imutável: `<base>/envs/duckdb-<versão>-<id>/` com duckdb, ipykernel e extensões offline.

Cada instalação cria um env novo, baixa as extensões do manifesto conferindo o sha256 do `.gz` e do
`.duckdb_extension`, valida o carregamento offline e só então troca o kernelspec e remove o env anterior.
Qualquer falha apaga o env novo e preserva o kernelspec anterior. Subprocessos usam lista de argumentos.
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
    remove_kernelspec,
    write_kernelspec,
)
from .manifest import (
    Manifest,
    ManifestError,
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
    """Another mutating job (install or remove) holds the DuckDB runtime lock."""


class NotInstalled(Exception):
    """No DuckDB runtime installed."""


class DuckDBInstaller:
    def __init__(
        self,
        base_dir: Path,
        jobs: JobRegistry,
        has_active_session: Callable[[str], bool] | None = None,
        manifest: Manifest | None = None,
    ) -> None:
        self.base_dir = Path(os.path.abspath(base_dir.expanduser()))
        self._jobs = jobs
        self._has_active_session = has_active_session or (lambda _name: False)
        self._manifest = manifest
        self._active: tuple[str, str] | None = None  # (job id, kind); `remove` has no job (empty id)
        self._download: asyncio.Future[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        self._env["UV_LINK_MODE"] = "copy"

    def is_mutating(self) -> bool:
        return self._active is not None

    def active_job(self) -> tuple[str, str] | None:
        """(job id, kind) of the install in progress, if any."""
        return self._active if self._active is not None and self._active[1] != "remove" else None

    def find(self) -> InstalledRuntime:
        entry = discover(self.base_dir)
        if entry is None:
            raise NotInstalled
        return entry

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Future[Any]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _load_manifest(self) -> Manifest:
        try:
            return self._manifest or load_manifest()
        except ManifestError as exc:
            raise InstallError(f"manifest: {exc}") from exc

    def start(self) -> Job:
        """Register the job and run it in the background; raises InstallInProgress on a duplicate."""
        if self.is_mutating():
            raise InstallInProgress
        manifest = self._load_manifest_or_none()
        job = self._jobs.create("install", manifest.duckdb_version if manifest else "")
        self._active = (job.id, "install")
        self._spawn(self._run(job))
        return job

    def _load_manifest_or_none(self) -> Manifest | None:
        try:
            return self._load_manifest()
        except InstallError:
            return None  # `_run` reports it as the job error

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def remove(self) -> asyncio.Future[None]:
        """Drop the kernelspec synchronously, then delete every env in a thread.

        Raises NotInstalled / InstallInProgress / RemoveFailed (kernelspec) before any env is touched;
        the future raises RemoveFailed with whatever is left.
        """
        if self.is_mutating():
            raise InstallInProgress
        entry = self.find()
        try:
            remove_kernelspec()
        except OSError as exc:
            raise RemoveFailed([str(kernels_dir() / KERNEL_NAME)]) from exc
        self._active = ("", "remove")
        return self._spawn(self._remove_envs(entry.env_dir))

    async def _remove_envs(self, env_dir: Path) -> None:
        try:
            await asyncio.to_thread(self._delete_all_envs, env_dir)
        finally:
            self._active = None

    def _delete_all_envs(self, env_dir: Path) -> None:
        envs = self.base_dir / ENVS_DIR
        pattern = re.compile(rf"{re.escape(ENV_PREFIX)}[^/]+-[0-9a-f]{{8}}")
        targets = {env_dir}
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

    def sweep_trash(self) -> None:
        """Delete `envs/.trash-duckdb-*` left by an interrupted removal; failures only warn."""
        envs = self.base_dir / ENVS_DIR
        if not envs.is_dir():
            return
        for old in envs.glob(f"{TRASH_PREFIX}{ENV_PREFIX}*"):
            if old.is_dir() and is_removable_env(self.base_dir, old):
                shutil.rmtree(old, ignore_errors=True)

    @staticmethod
    def _progress(phase: str) -> float:
        return PHASES.index(phase) / len(PHASES)

    async def _cmd(self, job: Job, phase: str, args: list[str]) -> list[str]:
        return await run_command(job, phase, args, self._env, self._progress(phase))

    async def _run(self, job: Job) -> None:
        env_dir: Path | None = None
        cancel = threading.Event()
        try:
            await job.start()
            manifest = self._load_manifest()
            await asyncio.to_thread(self.sweep_trash)
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
            await job.emit("kernelspec", f"writing kernelspec {KERNEL_NAME}", self._progress("kernelspec"))
            current = await asyncio.to_thread(discover, self.base_dir)
            previous = {current.env_dir} if current is not None else set()
            await asyncio.to_thread(write_kernelspec, manifest.duckdb_version, env_dir, manifest.names)
            installed, env_dir = env_dir, None  # switched: the new env must survive from here on
            await self._cleanup(job, installed, previous)
            await job.finish("succeeded")
        except asyncio.CancelledError:
            cancel.set()  # the download thread cannot be cancelled; it stops at the next chunk
            if self._download is not None and not self._download.done():
                await asyncio.wait({self._download}, timeout=DOWNLOAD_TIMEOUT)
            await self._discard(env_dir)
            await job.finish("failed", "cancelled")
            raise
        except InstallError as exc:
            await self._discard(env_dir)
            await job.finish("failed", str(exc))
        except Exception:
            log.exception("unexpected failure installing the DuckDB runtime")
            await self._discard(env_dir)
            await job.finish("failed", "unexpected error; see server log")
        finally:
            self._active = None
            self._download = None

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
            self._download = asyncio.ensure_future(
                asyncio.to_thread(self._fetch_extension, manifest, key, name, target, cancel)
            )
            try:
                await asyncio.shield(self._download)
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

    async def _cleanup(self, job: Job, installed: Path, previous: set[Path]) -> None:
        """Remove superseded envs; failures only warn (the install already succeeded)."""
        envs = self.base_dir / ENVS_DIR
        stale = {p for p in envs.glob(f"{ENV_PREFIX}*-????????") if p.is_dir()} | previous
        # A session opened during the install runs on the old env (`previous`); keep only that one.
        kept = (stale & previous) - {installed} if self._has_active_session(KERNEL_NAME) else set()
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
