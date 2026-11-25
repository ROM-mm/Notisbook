"""`notisbook --install-default-runtimes`: instala o DuckDB e o Spark padrão e termina, sem subir servidor.

Chamado pelo `install.sh` só na primeira instalação. Reaproveita os instaladores do app, no mesmo fluxo da UI.
Pula a família que já tem kernelspec gerenciado (idempotente) e o Spark sem JDK 17/21. Toma o flock do
backend para não competir com um app aberto na mesma pasta.
Exit: 0 nada falhou (inclui pulos), 1 algum runtime falhou, 2 não pôde rodar, 130 Ctrl+C. Mensagens em inglês.
"""

import asyncio
import os
import sys
from pathlib import Path

from ..config import default_home, default_pypi_url
from ..jobs import JobRegistry
from ..notislake.supervisor import LockBusyError, acquire_flock, lock_path
from ..runtimes.defaults import DEFAULT_DUCKDB_VERSION, DEFAULT_SPARK_VERSION
from ..runtimes.duckdb.installer import DuckDBInstaller, UnknownVersion
from ..runtimes.duckdb.manifest import ManifestError
from ..spark import kernelspec as spark_kernelspec
from ..spark.installer import InstallInProgress, ManagedInstaller, SparkInstaller
from ..spark.prereqs import jdk_candidates, jdk_for_spark

LOCK_DIR_MODE = 0o700


def _say(family: str, message: str) -> None:
    print(f"[{family}] {message}", flush=True)


async def _run_job(family: str, installer: ManagedInstaller, version: str) -> bool:
    """Roda o job de instalação e imprime seus eventos; True se terminou com sucesso."""
    try:
        job = installer.start(version)
    except (UnknownVersion, ManifestError, InstallInProgress) as exc:
        _say(family, f"failed: could not start the installation ({type(exc).__name__})")
        return False
    async for event in job.stream():
        _say(family, f"{event.phase}: {event.line}")
    return job.state == "succeeded"


async def _install_duckdb(installer: DuckDBInstaller) -> bool | None:
    """True instalou, False falhou, None pulou."""
    if installer.entries_of_all():
        _say("duckdb", "skipped: already installed")
        return None
    _say("duckdb", f"installing DuckDB {DEFAULT_DUCKDB_VERSION}")
    return await _run_job("duckdb", installer, DEFAULT_DUCKDB_VERSION)


async def _install_spark(installer: SparkInstaller, home: Path) -> bool | None:
    """True instalou, False falhou, None pulou (já instalado ou sem JDK)."""
    # `discover` compares paths textually; a relative NOTISBOOK_HOME must be normalized like the installers do.
    if spark_kernelspec.discover(Path(os.path.abspath(home))):
        _say("spark", "skipped: already installed")
        return None
    if await jdk_for_spark(DEFAULT_SPARK_VERSION) is None:
        wanted = " or ".join(str(m) for m in jdk_candidates(DEFAULT_SPARK_VERSION))
        _say("spark", f"skipped: no compatible JDK found (need JDK {wanted}); install one, then add Spark in Settings › Runtimes")
        return None
    _say("spark", f"installing Apache Spark {DEFAULT_SPARK_VERSION}")
    return await _run_job("spark", installer, DEFAULT_SPARK_VERSION)


async def _install_all(home: Path) -> int:
    jobs = JobRegistry()
    pypi_url = default_pypi_url()
    duckdb = DuckDBInstaller(home, jobs, pypi_url=pypi_url)
    spark = SparkInstaller(home, jobs, pypi_url=pypi_url)
    try:
        results = [await _install_duckdb(duckdb), await _install_spark(spark, home)]
    finally:
        # Ctrl+C cancela a tarefa principal; o cancelamento dos jobs é o que descarta o env pela metade.
        await duckdb.shutdown()
        await spark.shutdown()
    return 1 if any(r is False for r in results) else 0


def _take_lock(home: Path) -> int:
    """Flock do backend sem bloquear; cria `minio/`, que `ensure_home` não cria e o `lock_path` pressupõe."""
    lock = lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True, mode=LOCK_DIR_MODE)
    return acquire_flock(lock)


def run() -> int:
    """Instala os runtimes padrão; devolve o exit code (ver o docstring do módulo)."""
    home = default_home()
    try:
        lock_fd = _take_lock(home)
    except LockBusyError:
        print(f"Notisbook: another Notisbook is using the data folder {home}; close it and retry.", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Notisbook: cannot prepare the data folder {home} ({exc.strerror or exc}).", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_install_all(home))
    except KeyboardInterrupt:
        print("Notisbook: interrupted; the default runtimes were not fully installed.", file=sys.stderr)
        return 130
    finally:
        os.close(lock_fd)
