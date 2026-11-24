"""Versioned, immutable Spark environments.

Each install builds `<base>/envs/spark-<version>-<id>/`, validates it, and only
then switches the kernelspec and removes the previous directory. Any failure
deletes the new directory and leaves the previous kernelspec untouched.
Subprocesses always use an argument list, never a shell.
"""

import asyncio
import contextlib
import http.client
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
from asyncio.subprocess import DEVNULL, PIPE, STDOUT
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Literal

from ..catalog.store import ensure_catalog_db
from ..jobs import Job, JobRegistry
from .bundles import (
    S3A_BY_HADOOP,
    Bundle,
    S3aSet,
    UnsupportedHome,
    bundle_for,
    installed_hadoop,
    render_spark_defaults,
    write_log4j2,
)
# DOWNLOAD_CHUNK is re-exported for runtimes/duckdb/installer.py.
from .jar_cache import DOWNLOAD_CHUNK, DOWNLOAD_TIMEOUT, JarCache, JarError  # noqa: F401
from .kernelspec import (
    ENVS_DIR,
    TRASH_PREFIX,
    InstalledVersion,
    conf_dir,
    discover,
    is_removable_env,
    kernel_name,
    kernels_dir,
    remove_kernelspec,
    write_kernelspec,
)
from .packages import UvNotFound, package_env
from .prereqs import check_prereqs, jdk_candidates, jdk_for_spark
from .requirements import core_names

log = logging.getLogger(__name__)

PYTHON_VERSION = "3.12"
# Fixado: o ambiente é reprodutível e o `_validate` confere exatamente esta versão.
DUCKDB_VERSION = "2.0.0"
PHASES = ("prereqs", "python", "venv", "install", "bundle", "validate", "kernelspec", "cleanup")
STREAM_LIMIT = 1 << 20
# Leaking these would make the validation import a different pyspark than the venv's.
SCRUBBED_ENV = (
    "SPARK_HOME",
    "PYTHONPATH",
    "PYSPARK_PYTHON",
    "PYSPARK_DRIVER_PYTHON",
    "VIRTUAL_ENV",
    "PYSPARK_SUBMIT_ARGS",
    "SPARK_CONF_DIR",
)
# Teto do smoke: uma JVM travada não pode segurar o lock do kernel para sempre.
SMOKE_TIMEOUT = 300
# Starts a local session with the env's spark-defaults.conf. S3A part (always): loads S3AFileSystem and the SDK
# probe class, checks the Hadoop version and builds the s3a://notislake/ FileSystem with the closed config (dead
# endpoint, no credential). Formats part (argv[1] == "1", env with bundle): resolves one class per extension/catalog
# and lists the Iceberg namespaces, which opens the JDBC connection.
# argv: [1] formats 0|1, [2] SDK probe class, [3] expected Hadoop version, [4] URI of a throwaway SQLite file that
# already has the Iceberg tables (the catalog is configured not to create them), [5] throwaway local warehouse,
# so the smoke never writes to the real one or to s3a (works with MinIO stopped).
SMOKE_SCRIPT = """
import sys
from pyspark.sql import SparkSession
formats = sys.argv[1] == "1"
builder = (
    SparkSession.builder.master("local[1]")
    .config("spark.sql.warehouse.dir", sys.argv[5])
    .config("spark.ui.enabled", "false")
    .config("spark.ui.showConsoleProgress", "false")
    .config("spark.driver.bindAddress", "127.0.0.1")
    .config("spark.driver.host", "127.0.0.1")
)
if formats:
    builder = builder.config("spark.sql.catalog.iceberg.uri", sys.argv[4]).config(
        "spark.sql.catalog.iceberg.warehouse", sys.argv[5] + "/iceberg"
    )
spark = builder.getOrCreate()
jvm = spark.sparkContext._jvm
loader = jvm.Thread.currentThread().getContextClassLoader()
loader.loadClass("org.apache.hadoop.fs.s3a.S3AFileSystem")
loader.loadClass(sys.argv[2])
hadoop = jvm.org.apache.hadoop.util.VersionInfo.getVersion()
if hadoop != sys.argv[3]:
    raise SystemExit(f"Hadoop {hadoop} in pyspark does not match the S3A jars ({sys.argv[3]})")
spark.sql("SELECT 1").collect()
jvm.org.apache.hadoop.fs.FileSystem.get(jvm.java.net.URI.create("s3a://notislake/"), spark.sparkContext._jsc.hadoopConfiguration())
print("s3a-smoke-ok")
if formats:
    for key in ("spark.sql.extensions", "spark.sql.catalog.spark_catalog", "spark.sql.catalog.iceberg", "spark.kryo.registrator"):
        for cls in spark.conf.get(key).split(","):
            loader.loadClass(cls)
    spark.sql("SHOW NAMESPACES IN iceberg").collect()
    print("formats-smoke-ok")
spark.stop()
"""


class InstallError(Exception):
    """A phase failed; the message is user-facing (job error and log)."""


class InstallInProgress(Exception):
    """Another mutating job (install, libs, remove) holds the lock of this kernel name."""


class RemoveFailed(Exception):
    """Part of an environment could not be deleted; `paths` lists what is left."""

    def __init__(self, paths: list[str]) -> None:
        super().__init__("could not delete: " + ", ".join(paths))
        self.paths = paths


class VersionNotFound(Exception):
    """No installed Spark version with that number."""


async def run_command(
    job: Job, phase: str, args: list[str], env: dict[str, str], progress: float | None
) -> list[str]:
    """Run `args` streaming its output to the job; `progress=None` leaves the bar indeterminate."""
    await job.emit(phase, "$ " + " ".join(args), progress)
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, env=env, limit=STREAM_LIMIT
        )
    except OSError as exc:
        raise InstallError(f"{phase}: cannot start {args[0]}: {exc.strerror}") from exc
    lines: list[str] = []
    try:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                lines.append(line)
                await job.emit(phase, line, progress)
        code = await proc.wait()
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
    if code != 0:
        raise InstallError(f"{phase} failed (exit {code})")
    return lines


class ManagedInstaller:
    """Per-kernel lock, task tracking and libs ("packages") jobs shared by the Spark and DuckDB installers.

    Subclasses set `label`/`PACKAGES_KIND` and implement `find`, `lock_name` and `session_names`.
    """

    label = ""
    PACKAGES_KIND = "packages"

    def __init__(
        self,
        base_dir: Path,
        jobs: JobRegistry,
        has_active_session: Callable[[str], bool] | None = None,
        pypi_url: str = "https://pypi.org",
    ) -> None:
        self.base_dir = Path(os.path.abspath(base_dir.expanduser()))
        self._jobs = jobs
        self._has_active_session = has_active_session or (lambda _name: False)
        self._pypi_url = pypi_url
        # kernel name -> (job id, kind); `remove` has no job (empty id).
        self._active: dict[str, tuple[str, str]] = {}
        # kernel name -> ação do job de libs em andamento (add/upgrade/uninstall).
        self._package_actions: dict[str, str] = {}
        self._downloads: dict[str, asyncio.Future[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        self._env["UV_LINK_MODE"] = "copy"

    def find(self, version: str) -> Any:
        """Installed entry (with `kernel_name` and `env_dir`) of the version; raises VersionNotFound."""
        raise NotImplementedError

    def lock_name(self, version: str, entry: Any = None) -> str:
        """Kernel name that carries the lock of the version's jobs."""
        raise NotImplementedError

    def session_names(self, version: str) -> set[str]:
        """Kernel names whose active session blocks changing the version."""
        raise NotImplementedError

    def core_names(self, version: str) -> set[str]:
        """Canonical names of the libs the user cannot change (base libs of the env)."""
        raise NotImplementedError

    def try_acquire(self, name: str, job_id: str, kind: str) -> bool:
        """Take the per-kernel lock shared by install, libs and remove; False when it is held."""
        if name in self._active:
            return False
        self._active[name] = (job_id, kind)
        return True

    def release(self, name: str) -> None:
        self._active.pop(name, None)
        self._package_actions.pop(name, None)

    def package_action(self, name: str) -> str | None:
        """Action of the libs job holding the lock of `name`, if any."""
        held = self._active.get(name)
        return self._package_actions.get(name) if held is not None and held[1] == self.PACKAGES_KIND else None

    def is_mutating(self, name: str, kind: str | None = None) -> bool:
        """True while the lock of `name` is held (by a job of `kind`, when given)."""
        held = self._active.get(name)
        return held is not None and (kind is None or held[1] == kind)

    def active_jobs(self) -> dict[str, tuple[str, str]]:
        """Kernel name -> (job id, kind) for install/libs jobs in progress."""
        return {name: held for name, held in self._active.items() if held[1] != "remove"}

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Future[Any]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def start_packages(self, version: str, action: str, argv_builder: Callable[[str, str, str], list[str]]) -> Job:
        """Run an `uv pip` command on the installed env as a libs job (`PACKAGES_KIND`).

        `argv_builder(uv, python, pypi_url)` builds the command. Raises VersionNotFound,
        UvNotFound or InstallInProgress before any change; callers check sessions with no await in between.
        """
        entry = self.find(version)
        uv = shutil.which("uv")
        if uv is None:
            raise UvNotFound
        name = self.lock_name(version, entry)
        if self.is_mutating(name):
            raise InstallInProgress(version)
        args = argv_builder(uv, str(entry.env_dir / "bin" / "python"), self._pypi_url)
        job = self._jobs.create(self.PACKAGES_KIND, version)
        self.try_acquire(name, job.id, self.PACKAGES_KIND)
        self._package_actions[name] = action
        self._spawn(self._run_packages(job, name, action, args))
        return job

    def packages_env(self) -> dict[str, str]:
        return package_env(self._env)

    @property
    def pypi_url(self) -> str:
        return self._pypi_url

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


    async def _run_packages(self, job: Job, name: str, action: str, args: list[str]) -> None:
        try:
            await job.start()
            await run_command(job, "packages", args, self.packages_env(), None)
            await self._finish_packages(job, name, "succeeded")
        except asyncio.CancelledError:
            await self._finish_packages(job, name, "failed", "cancelled")
            raise
        except InstallError as exc:
            await self._finish_packages(job, name, "failed", f"{action}: {exc}")
        except Exception:
            log.exception("unexpected failure running libs job (%s)", action)
            await self._finish_packages(job, name, "failed", "unexpected error; see server log")

    async def _finish_packages(
        self, job: Job, name: str, state: Literal["succeeded", "failed"], error: str | None = None
    ) -> None:
        # Libera o lock antes do evento `done`: o cliente reage a ele e já pode pedir outra ação.
        if self._active.get(name, ("",))[0] == job.id:
            self.release(name)
        await job.finish(state, error)


class SparkInstaller(ManagedInstaller):
    label = "Spark"

    def __init__(
        self,
        base_dir: Path,
        jobs: JobRegistry,
        has_active_session: Callable[[str], bool] | None = None,
        pypi_url: str = "https://pypi.org",
    ) -> None:
        super().__init__(base_dir, jobs, has_active_session, pypi_url)
        # One cache per installer: its pins and in-flight downloads must be shared by every install job.
        self._jars = JarCache(self.base_dir)

    def find(self, version: str) -> InstalledVersion:
        entry = next((e for e in discover(self.base_dir) if e.version == version), None)
        if entry is None:
            raise VersionNotFound(version)
        return entry

    def lock_name(self, version: str, entry: Any = None) -> str:
        return entry.kernel_name if entry is not None else kernel_name(version)

    def session_names(self, version: str) -> set[str]:
        return {kernel_name(version)}

    def core_names(self, version: str) -> set[str]:
        return core_names(version)

    def start(self, version: str) -> Job:
        """Register the job and run it in the background; raises InstallInProgress on a duplicate.

        The lock is per kernel name, which also serialises `3.5.10`/`3.51.0` (same `spark3510`).
        """
        name = kernel_name(version)
        if self.is_mutating(name):
            raise InstallInProgress(version)
        job = self._jobs.create("install", version)
        self.try_acquire(name, job.id, "install")
        self._spawn(self._run(job, version, name))
        return job

    def remove(self, version: str) -> asyncio.Future[None]:
        """Drop the kernelspec synchronously, then delete every env of the version in a thread.

        The synchronous part lets the caller check sessions and remove without an
        await in between. Raises VersionNotFound / InstallInProgress / RemoveFailed
        (kernelspec) before any env is touched; the future raises RemoveFailed with leftovers.
        """
        name = kernel_name(version)
        if self.is_mutating(name):
            raise InstallInProgress(version)
        entry = self.find(version)
        try:
            remove_kernelspec(self.base_dir, entry.kernel_name)
        except OSError as exc:
            raise RemoveFailed([str(kernels_dir(self.base_dir) / entry.kernel_name)]) from exc
        self.try_acquire(name, "", "remove")
        return self._spawn(self._remove_envs(name, version, entry.env_dir))

    async def _remove_envs(self, name: str, version: str, env_dir: Path) -> None:
        try:
            await asyncio.to_thread(self._delete_version_envs, version, env_dir)
        finally:
            self.release(name)

    def _delete_version_envs(self, version: str, env_dir: Path) -> None:
        """Move each env of the version to `envs/.trash-*` and delete it; raise with whatever is left."""
        envs = self.base_dir / ENVS_DIR
        pattern = re.compile(rf"spark-{re.escape(version)}-[0-9a-f]{{8}}")
        targets = {env_dir}
        if envs.is_dir():
            targets |= {p for p in envs.iterdir() if pattern.fullmatch(p.name) and p.is_dir()}
        left: list[str] = []
        for target in sorted(targets):
            if not is_removable_env(self.base_dir, target):
                log.warning("refusing to delete %s: outside the managed locations", target)
                left.append(str(target))
                continue
            doomed = target
            if target.parent == envs:
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
            try:
                shutil.rmtree(doomed)
            except OSError:
                log.warning("could not delete %s", doomed, exc_info=True)
                left.append(str(doomed))
            else:
                if doomed.exists():
                    left.append(str(doomed))
        self._collect_jars()
        if left:
            raise RemoveFailed(left)

    def _collect_jars(self) -> None:
        """Drop cached jars no env references anymore; never fails the caller (the env work already finished)."""
        try:
            self._jars.collect_garbage()
        except Exception:
            log.warning("jar cache garbage collection failed", exc_info=True)

    def sweep_trash(self, version: str | None = None) -> None:
        """Delete `envs/.trash-spark-*` left by an interrupted removal; failures only warn.

        With `version`, sweeps only that version's leftovers (the caller holds its kernel lock),
        so a concurrent removal of another version is not raced.
        """
        envs = self.base_dir / ENVS_DIR
        if not envs.is_dir():
            return
        stem = f"spark-{version}-*" if version else "spark-*"
        for old in envs.glob(f"{TRASH_PREFIX}{stem}"):
            if old.is_dir() and is_removable_env(self.base_dir, old):
                shutil.rmtree(old, ignore_errors=True)

    async def _run(self, job: Job, version: str, name: str) -> None:
        env_dir: Path | None = None
        cancel = threading.Event()
        try:
            await job.start()
            await asyncio.to_thread(lambda: self.sweep_trash(version))
            uv, java_home = await self._check_prereqs(job, version)
            await self._cmd(job, "python", [uv, "python", "install", PYTHON_VERSION])
            env_dir = self.base_dir / ENVS_DIR / f"spark-{version}-{uuid.uuid4().hex[:8]}"
            env_dir.parent.mkdir(parents=True, exist_ok=True)
            await self._cmd(job, "venv", [uv, "venv", str(env_dir), "--python", PYTHON_VERSION])
            python = str(env_dir / "bin" / "python")
            bundle = bundle_for(version)
            packages = [f"pyspark=={version}", "ipykernel", f"duckdb=={DUCKDB_VERSION}", *(bundle.pip if bundle else ())]
            await self._cmd(job, "install", [uv, "pip", "install", "--python", python, *packages])
            try:
                await asyncio.to_thread(write_log4j2, conf_dir(env_dir))
            except OSError as exc:
                raise InstallError(f"log4j2: cannot write {conf_dir(env_dir)}: {exc}") from exc
            s3a = await self._detect_s3a(job, env_dir, version)
            await self._install_bundle(job, env_dir, version, bundle, s3a, cancel)
            await self._validate(job, python, version, env_dir, java_home, bundle, s3a)
            await job.emit("kernelspec", f"writing kernelspec {name}", self._progress("kernelspec"))
            previous = {e.env_dir for e in discover(self.base_dir) if e.kernel_name == name}
            await asyncio.to_thread(write_kernelspec, self.base_dir, version, env_dir, java_home, s3a)
            installed, env_dir = env_dir, None  # switched: the new env must survive from here on
            await self._cleanup(job, version, installed, previous)
            self._jars.unpin(job.id)
            await asyncio.to_thread(self._collect_jars)
            await job.finish("succeeded")
        except asyncio.CancelledError:
            cancel.set()  # the download thread cannot be cancelled; it stops at the next chunk
            if (download := self._downloads.get(name)) is not None and not download.done():
                # Bounded wait so the thread is not still writing into env_dir when it is deleted.
                await asyncio.wait({download}, timeout=DOWNLOAD_TIMEOUT)
            await self._discard(env_dir, job)
            await job.finish("failed", "cancelled")
            raise
        except InstallError as exc:
            await self._discard(env_dir, job)
            await job.finish("failed", str(exc))
        except Exception:
            log.exception("unexpected failure installing Spark %s", version)
            await self._discard(env_dir, job)
            await job.finish("failed", "unexpected error; see server log")
        finally:
            self._jars.unpin(job.id)
            self.release(name)
            self._downloads.pop(name, None)

    @staticmethod
    def _progress(phase: str) -> float:
        return PHASES.index(phase) / len(PHASES)

    async def _check_prereqs(self, job: Job, version: str) -> tuple[str, str]:
        progress = self._progress("prereqs")
        prereqs = await check_prereqs()
        uv = shutil.which("uv")
        if uv is None:
            raise InstallError("uv not found; install it with: brew install uv")
        java_home = await jdk_for_spark(version)
        if java_home is None:
            wanted = " or ".join(str(m) for m in jdk_candidates(version))
            raise InstallError(f"no compatible JDK for Spark {version}: install JDK {wanted}")
        await job.emit("prereqs", f"uv {prereqs.uv_version}", progress)
        await job.emit("prereqs", f"JAVA_HOME={java_home}", progress)
        name = kernel_name(version)
        clash = next((e for e in discover(self.base_dir) if e.kernel_name == name and e.version != version), None)
        if clash is not None:
            raise InstallError(f"kernel name {name} is already used by Spark {clash.version}")
        return uv, java_home

    async def _cmd(self, job: Job, phase: str, args: list[str], env: dict[str, str] | None = None) -> list[str]:
        return await run_command(job, phase, args, env or self._env, self._progress(phase))

    async def _detect_s3a(self, job: Job, env_dir: Path, version: str) -> S3aSet:
        """S3A jar set for the Hadoop inside the installed pyspark; an unknown Hadoop fails closed."""
        hadoop = await asyncio.to_thread(installed_hadoop, env_dir)
        s3a = S3A_BY_HADOOP.get(hadoop) if hadoop is not None else None
        if s3a is None:
            raise InstallError(
                f"Hadoop {hadoop or 'not detected'} has no pinned S3A jar set; Spark {version} is not supported yet"
            )
        await job.emit("install", f"S3A: pyspark ships Hadoop {hadoop}, S3A set r{s3a.revision}", self._progress("install"))
        return s3a

    async def _install_bundle(
        self, job: Job, env_dir: Path, version: str, bundle: Bundle | None, s3a: S3aSet, cancel: threading.Event
    ) -> None:
        """Download the S3A jars (and the bundle's, if any) into the shared cache and write `spark-defaults.conf`."""
        progress = self._progress("bundle")
        name = kernel_name(version)
        self._render_defaults(bundle, s3a)  # fails before any download when the home cannot go in the JDBC URL
        if bundle is None:
            await job.emit(
                "bundle",
                f"no Delta/Iceberg/Hudi bundle for Spark {version}; installing S3A only, sessions open without the formats",
                progress,
            )
        artifacts = [*(bundle.artifacts if bundle else ()), *(bundle.driver_artifacts if bundle else ()), *s3a.artifacts]
        # Pinned until the job ends: the conf that references these jars is only written after the last download.
        self._jars.pin(job.id, artifacts)
        s3a_names = {a.filename for a in s3a.artifacts}
        for artifact in artifacts:
            tag = " (S3A)" if artifact.filename in s3a_names else ""
            await job.emit("bundle", f"downloading{tag} {artifact.coordinates}", progress)
            # Shielded and tracked so a cancelled job can still wait for the thread to stop.
            download = asyncio.ensure_future(asyncio.to_thread(self._jars.ensure, artifact, cancel))
            self._downloads[name] = download
            try:
                await asyncio.shield(download)
            except (OSError, http.client.HTTPException, JarError) as exc:
                raise InstallError(f"bundle: cannot download {artifact.filename}: {exc}") from exc
            await job.emit("bundle", f"verified sha256{tag} {artifact.sha256} {artifact.filename}", progress)
        conf = conf_dir(env_dir)
        content = self._render_defaults(bundle, s3a)
        await asyncio.to_thread(conf.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((conf / "spark-defaults.conf").write_text, content, "utf-8")
        await job.emit("bundle", f"S3A r{s3a.revision} ready: Hadoop {s3a.hadoop}, jars in {self._jars.root}", progress)
        if bundle is not None:
            await job.emit("bundle", f"bundle {bundle.line} r{bundle.revision}: {', '.join(bundle.formats)}", progress)

    def _render_defaults(self, bundle: Bundle | None, s3a: S3aSet) -> str:
        try:
            return render_spark_defaults(bundle, s3a, self._jars.path, self.base_dir)
        except UnsupportedHome as exc:
            raise InstallError(f"bundle: {exc}") from exc

    async def _validate(
        self, job: Job, python: str, version: str, env_dir: Path, java_home: str, bundle: Bundle | None, s3a: S3aSet
    ) -> None:
        lines = await self._cmd(job, "validate", [python, "-I", "-c", "import pyspark; print(pyspark.__version__)"])
        found = lines[-1] if lines else None
        if found != version:
            raise InstallError(f"installed pyspark is {found}, expected {version}")
        lines = await self._cmd(job, "validate", [python, "-I", "-c", "import duckdb; print(duckdb.__version__)"])
        found = lines[-1] if lines else None
        if found != DUCKDB_VERSION:
            raise InstallError(f"installed duckdb is {found}, expected {DUCKDB_VERSION}")
        smoke_env = {**self._env, "JAVA_HOME": java_home, "SPARK_CONF_DIR": str(conf_dir(env_dir)), "PYSPARK_PYTHON": python}
        # The real catalog.db must not be touched by an install: the smoke uses a throwaway SQLite file.
        with tempfile.TemporaryDirectory(prefix="notisbook-smoke-") as scratch:
            uri = ""
            if bundle is not None:
                # O JdbcCatalog roda com `init-catalog-tables false`: o DDL de produção é aplicado antes do smoke.
                try:
                    await asyncio.to_thread(ensure_catalog_db, Path(scratch))
                except sqlite3.Error as exc:
                    raise InstallError(f"smoke test could not prepare its catalog: {exc}") from exc
                uri = f"jdbc:sqlite:{Path(scratch) / 'catalog.db'}"
            warehouse = (Path(scratch) / "warehouse").as_uri()
            args = [python, "-I", "-c", SMOKE_SCRIPT, "1" if bundle else "0", s3a.sdk_probe_class, s3a.hadoop, uri, warehouse]
            try:
                # `wait_for` cancela o `run_command`, cujo `finally` mata o processo.
                lines = await asyncio.wait_for(self._cmd(job, "validate", args, smoke_env), SMOKE_TIMEOUT)
            except TimeoutError as exc:
                raise InstallError(f"smoke test timed out after {SMOKE_TIMEOUT}s") from exc
            except InstallError as exc:
                raise InstallError(f"smoke test failed: {exc}") from exc
        # stderr is merged into stdout: a Spark progress bar (`\r`-redrawn, no newline) can prefix the marker line.
        # Only the last `\r` segment counts, compared whole, so the echoed script text never matches.
        printed = {line.rsplit("\r", 1)[-1].strip() for line in lines}
        if "s3a-smoke-ok" not in printed:
            raise InstallError("S3A smoke test did not complete")
        if bundle is not None and "formats-smoke-ok" not in printed:
            raise InstallError("formats smoke test did not complete")

    async def _cleanup(self, job: Job, version: str, installed: Path, previous: set[Path]) -> None:
        """Remove superseded dirs of this version; failures only warn (the install already succeeded)."""
        envs = self.base_dir / ENVS_DIR
        stale = {p for p in envs.glob(f"spark-{version}-????????") if p.is_dir()} | previous
        # A session opened during the install runs on the old env (`previous`); keep only that one.
        in_use = previous if self._has_active_session(kernel_name(version)) else set()
        kept = (stale & in_use) - {installed}
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

    async def _discard(self, env_dir: Path | None, job: Job) -> None:
        """Delete the half-built env, release the job's jar pins and drop jars nothing references anymore."""
        if env_dir is not None:
            await asyncio.to_thread(self._delete_env, env_dir)
        self._jars.unpin(job.id)
        await asyncio.to_thread(self._collect_jars)
