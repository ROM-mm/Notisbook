"""Kernel sessions on top of `jupyter_client`.

This is the only module that imports `jupyter_client`, so the backend can be
swapped for `jupyter_server` without touching the API or the WS protocol.
"""

import asyncio
import contextlib
import logging
import os
import shutil
import sys
import uuid
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.parse import urlsplit

from jupyter_client.asynchronous.client import AsyncKernelClient
from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel
from jupyter_client.manager import AsyncKernelManager
from jupyter_core.paths import jupyter_runtime_dir
from nbformat.v4 import output_from_msg

from ..catalog.store import catalog_db_path
from ..config import RUNTIME_HOST, Settings
from ..notislake import objectstore, settings_store
from ..notislake.sparkconf import fingerprint, s3a_options
from ..notislake.supervisor import NotislakeSupervisor
from ..runtimes.docker import catalog as docker_catalog
from ..runtimes.docker import cli as docker_cli
from ..runtimes.docker import kernelspec as docker_spec
from ..runtimes.docker import launch as docker_launch
from ..runtimes.docker.service import (
    ContainerForeign,
    ContainerInfo,
    ContainerMissing,
    DockerRuntimes,
    DockerUnavailable,
    InstallInProgress,
    MountPlan,
    MountRejected,
    SessionsActive,
    inspect_container,
)
from ..runtimes.duckdb import kernelspec as duckdb_kernelspec
from ..runtimes.duckdb.hook import build_bootstrap_code as build_duckdb_bootstrap_code
from ..runtimes.duckdb.kernelspec import KERNEL_NAME as DUCKDB_KERNEL_NAME
from ..runtimes.duckdb.kernelspec import METADATA_KEY as DUCKDB_METADATA_KEY
from ..runtimes.duckdb.kernelspec import is_duckdb_kernel_name
from ..security import RuntimeGrant, RuntimeTokens
from ..spark.bundles import (
    UnsupportedHome,
    bundle_for,
    render_spark_defaults,
    safety_warehouse_uri,
    write_log4j2,
    write_spark_defaults,
)
from ..spark import kernelspec as spark_kernelspec
from ..spark.jar_cache import JarCache
from ..spark.kernelspec import (
    METADATA_KEY,
    TRASH_PREFIX,
    PythonState,
    copy_kernel_json,
    is_managed_env,
    is_spark_kernel_name,
    jars_dir,
    kernels_dir,
    legacy_kernels_dir,
    python_usable,
    s3a_plan,
)
from .catalog_hook import build_ensure_code as build_catalog_ensure_code
from .catalog_hook import build_http_ensure_code as build_catalog_http_ensure_code
from .languages import CELL_LANGUAGE_LABELS, CellLanguage
from .protocol import (
    ClearOutputEvent,
    ErrorEvent,
    ExecuteInputEvent,
    ExecuteReplyEvent,
    KernelState,
    OutputEvent,
    ServerEvent,
    StatusEvent,
)
from .sql_cell import (
    MODULE_NAME,
    build_duckdb_code,
    build_duckdb_kernel_code,
    build_ensure_code,
)
from .sql_cell import build_code as build_sql_code

log = logging.getLogger(__name__)

# Leaking these would make the kernel resolve a different Spark than its kernelspec.
SCRUBBED_ENV = (
    "SPARK_HOME",
    "PYTHONPATH",
    "PYSPARK_PYTHON",
    "PYSPARK_DRIVER_PYTHON",
    "PYSPARK_SUBMIT_ARGS",
    "SPARK_CONF_DIR",
)
STREAM_LIMIT_BYTES = 1_000_000
LIVENESS_INTERVAL = 2.0
READY_TIMEOUT = 60.0
IDLE_GRACE = 2.0
SHUTDOWN_WAIT = 2.0
ENSURE_WAIT = 3.0
ENSURE_CHECK = f"__import__('sys').modules.get({MODULE_NAME!r}) is not None"
TRUNCATION_NOTICE = "\n[output truncated: 1 MB limit per cell reached]\n"
DOCKER_KERNEL_PREFIX = "notisbook-docker-"
# Limites do ramo Docker: o encerramento do app e o fechamento de sessão não podem ficar presos no CLI.
DOCKER_KILL_WAIT = 10.0
DOCKER_SWEEP_WAIT = 25.0
DOCKER_STOP_WAIT = 25.0
DOCKER_STOP_SKIPPED = (
    TimeoutError,
    ContainerMissing,
    ContainerForeign,
    DockerUnavailable,
    InstallInProgress,
    SessionsActive,
    docker_cli.DockerError,
    OSError,
)

Sink = Callable[[ServerEvent], Awaitable[None]]

# Textos fixos de S3A: nada da conexão ou da configuração entra na mensagem.
CONFIG_INVALID_CODE = "config_invalid"
CONFIG_INVALID_MESSAGE = "A configuração manual do notislake está inválida; corrija ou remova-a."
NOTISLAKE_UNAVAILABLE_CODE = "notislake_unavailable"
SPARK_ENV_OUTDATED_CODE = "spark_env_outdated"
SPARK_ENV_OUTDATED_MESSAGE = (
    "O runtime deste kernel não tem os jars S3A da versão atual; reinstale-o em Settings › Runtimes."
)
RUNTIME_NOT_INSTALLED_CODE = "runtime_not_installed"
RUNTIME_NOT_INSTALLED_MESSAGE = (
    "O runtime deste kernel não está instalado ou seu ambiente foi removido; instale-o em Settings › Runtimes."
)
S3A_LOOPBACK_HTTPS_NOTICE = (
    "s3a_unsupported_endpoint",
    "Endpoint https em localhost não é suportado no runtime Docker: a troca de host invalida o certificado.",
)


class KernelNotFound(Exception):
    """No kernelspec with the requested name."""


class KernelsBusy(Exception):
    """Há célula em execução; a operação que exige os kernels ociosos foi recusada."""


class SessionNotFound(Exception):
    """No session with the requested id."""


class NotislakeUnavailable(Exception):
    """O MinIO local (notislake) não está em `running`; nenhuma sessão nova é aberta até ele voltar."""

    def __init__(self, state: str) -> None:
        super().__init__(f"notislake is not running (state: {state})")
        self.state = state

    @property
    def message(self) -> str:
        return f"O notislake (MinIO) não está disponível (estado: {self.state}); tente de novo quando ele estiver em execução."


class SparkEnvOutdated(Exception):
    """O ambiente Spark gerenciado não tem todos os jars S3A (ou do bundle) que o conf nomeia; ele manteria o warehouse local."""


class RuntimeNotInstalled(Exception):
    """Kernel com nome do Notisbook cujo kernelspec ou interpretador não existe (runtime não instalado ou env removido)."""

    def __init__(self, kernel_name: str) -> None:
        super().__init__(f"runtime not installed: {kernel_name}")
        self.kernel_name = kernel_name


@dataclass(frozen=True)
class S3AResolution:
    """Conexão S3A de uma abertura de kernel; sem `options` o kernel sobe sem S3A. Carrega o segredo: fora de `repr`."""

    options: dict[str, str] | None = field(default=None, repr=False)
    fingerprint: str | None = field(default=None, repr=False)
    notice: tuple[str, str] | None = None


class DockerRuntimeError(Exception):
    """O runtime Docker não pode abrir a sessão agora; `status_code` é o HTTP correspondente e a mensagem vai ao operador."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class _Pending:
    cell_id: str
    reply: ExecuteReplyEvent | None = None
    idle: bool = False


RuntimeKind = Literal["duckdb", "docker", "local"]

# Fonte única de "linguagem de célula x kernel"; a ordem é a canônica do seletor (python, sql, duckdb).
CELL_LANGUAGES_BY_KIND: dict[RuntimeKind, tuple[CellLanguage, ...]] = {
    "local": ("python", "sql", "duckdb"),
    "duckdb": ("python", "duckdb"),
    "docker": ("python", "sql"),
}
CELL_LANGUAGES_NON_PYTHON_KERNEL: tuple[CellLanguage, ...] = ("python",)
RUNTIME_KIND_LABELS: dict[RuntimeKind, str] = {"duckdb": "DuckDB", "docker": "Docker", "local": "local"}


class KernelSpecInfo(TypedDict):
    name: str
    display_name: str
    language: str
    cell_languages: list[CellLanguage]
    runtime_kind: RuntimeKind


def runtime_kind(kernel_name: str, metadata: object, docker: bool | None = None) -> RuntimeKind:
    """Tipo de runtime do kernel, na precedência do despacho: duckdb > docker > local.

    DuckDB: nome `duckdb` ou `duckdb-<maj>-<min>-<patch>` e a chave `notisbook_duckdb` no metadata do kernelspec. Docker: nome no catálogo,
    ou `docker` quando o chamador já o consultou. `metadata` que não seja dict conta como vazio.
    """
    if is_duckdb_kernel_name(kernel_name) and isinstance(metadata, dict) and DUCKDB_METADATA_KEY in metadata:
        return "duckdb"
    if docker is None:
        docker = docker_catalog.by_kernel_name(kernel_name) is not None
    return "docker" if docker else "local"


def cell_languages_for(kind: RuntimeKind, spec_language: str) -> tuple[CellLanguage, ...]:
    """Linguagens de célula executáveis no kernel; kernel que não é Python (R, Julia) só roda `python`."""
    if spec_language != "python":
        return CELL_LANGUAGES_NON_PYTHON_KERNEL
    return CELL_LANGUAGES_BY_KIND[kind]


def _unavailable_message(language: CellLanguage, kind: RuntimeKind, spec_language: str) -> str:
    label = CELL_LANGUAGE_LABELS[language]
    if spec_language != "python":
        where = "in non-Python kernels"
    else:
        where = f"in the {RUNTIME_KIND_LABELS[kind]} kernel"
    return f"{label} is not available {where}. Change the cell language or the kernel."


@dataclass
class KernelSession:
    session_id: str
    path: str
    kernel_name: str
    manager: AsyncKernelManager
    state: KernelState = "starting"
    sink: Sink | None = None
    client: AsyncKernelClient | None = None
    pending: dict[str, _Pending] = field(default_factory=dict)
    stream_bytes: dict[str, int] = field(default_factory=dict)
    closing: bool = False
    # Reservado por `KernelService.reserve_idle`: `execute` recusa células enquanto durar.
    blocked: bool = False
    # Caminho absoluto resolvido do notebook no momento da criação (base de has_session_under).
    target: Path | None = None
    # Pasta de extensões do DuckDB (derivada do home injetado no KernelService).
    duckdb_ext_dir: str = ""
    # Snippet that installs the catalog hook (paths derived from the home injected in KernelService).
    # Carrega o segredo S3A: fora do `repr` do dataclass.
    catalog_ensure: str = field(default="", repr=False)
    # Runtime Docker da sessão (None no Local) e tag do kernel no container, usada pelo reaper do close.
    docker_runtime: docker_catalog.DockerRuntime | None = None
    docker_tag: str = ""
    # Token de runtime da sessão Docker ou DuckDB: emitido na criação, trocado no restart, revogado no close.
    runtime_tokens: RuntimeTokens | None = None
    runtime_grant: RuntimeGrant | None = None
    # Kernel do runtime DuckDB: conexão própria, sem hook Spark; `catalog_ensure` traz o bootstrap dela (com o token).
    duckdb_kernel: bool = False
    # Tipo de runtime, linguagem do kernelspec e linguagens de célula que o kernel executa (`execute()` recusa as demais).
    kind: RuntimeKind = "local"
    spec_language: str = "python"
    cell_languages: tuple[CellLanguage, ...] = CELL_LANGUAGES_BY_KIND["local"]
    # Monta o snippet do hook (Docker: catálogo; DuckDB: bootstrap) a partir do token e das opções S3A; None deixa o hook desligado.
    catalog_factory: Callable[[str, Mapping[str, str] | None], str] | None = None
    # Sessão local: monta o snippet a partir das opções S3A (o hook local fala com o SQLite, sem token).
    local_catalog_factory: Callable[[Mapping[str, str] | None], str] | None = None
    # Reavalia a conexão S3A no restart e levanta se ela não servir; None mantém a conexão com que a sessão abriu.
    s3a_resolver: Callable[[], S3AResolution] | None = None
    _s3a_options: dict[str, str] | None = field(default=None, repr=False)
    # Aviso da abertura (ex.: endpoint não suportado); o canal o entrega uma vez, como o do restart.
    s3a_notice: tuple[str, str] | None = None
    _restarting: bool = False
    _channel_tasks: list[asyncio.Task[None]] = field(default_factory=list)
    _ready_task: asyncio.Task[None] | None = None
    _bg_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    _probes: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def take_s3a_notice(self) -> tuple[str, str] | None:
        """Devolve o aviso de abertura pendente e o limpa (entregue uma única vez)."""
        notice, self.s3a_notice = self.s3a_notice, None
        return notice

    def info(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "path": self.path,
            "kernel_name": self.kernel_name,
            "state": self.state,
        }

    async def emit(self, event: ServerEvent) -> None:
        sink = self.sink
        if sink is None:
            return
        try:
            await sink(event)
        except Exception:  # a broken socket must not kill the readers
            log.debug("sink failed for session %s", self.session_id, exc_info=True)

    async def set_state(self, state: KernelState) -> None:
        if self.state == state:
            return
        self.state = state
        await self.emit(StatusEvent(state=state))

    def _spawn(self, coro: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    async def start(self, env: dict[str, str], cwd: Path | None) -> None:
        kwargs: dict[str, Any] = {"env": env}
        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        await self.manager.start_kernel(**kwargs)
        self._open_channels()
        self._spawn(self._monitor())

    def _open_channels(self) -> None:
        """Connect a fresh client; readers start only after `wait_for_ready`.

        `wait_for_ready` consumes the shell channel itself, so a concurrent
        reader would steal its kernel_info reply.
        """
        client = self.manager.client()
        client.start_channels()
        self.client = client
        self._ready_task = self._spawn(self._await_ready(client))

    def _start_readers(self, client: AsyncKernelClient) -> None:
        self._channel_tasks = [
            asyncio.ensure_future(self._guard(self._iopub_loop(client))),
            asyncio.ensure_future(self._guard(self._shell_loop(client))),
        ]

    async def _close_channels(self) -> None:
        tasks, self._channel_tasks = self._channel_tasks, []
        if self._ready_task is not None:
            tasks.append(self._ready_task)
            self._ready_task = None
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.client is not None:
            with contextlib.suppress(Exception):
                self.client.stop_channels()
            self.client = None

    async def _guard(self, loop: Awaitable[None]) -> None:
        try:
            await loop
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("channel reader failed for session %s", self.session_id)
            await self._mark_dead()

    def issue_runtime_token(self) -> None:
        """Emite um token novo (o anterior deixa de valer) e, havendo fábrica, regenera o snippet do hook."""
        if self.runtime_tokens is None or self.runtime_grant is None:
            return
        token = self.runtime_tokens.issue(self.runtime_grant)
        if self.catalog_factory is not None:
            self.catalog_ensure = self.catalog_factory(token, self._s3a_options)

    def refresh_s3a(self) -> tuple[str, str] | None:
        """Reavalia a conexão S3A para o kernel novo; levanta `ConfigInvalid` ou `NotislakeUnavailable` sem alterar a sessão.

        Atualiza o fingerprint do grant e o snippet local; o snippet Docker e o bootstrap DuckDB saem de `issue_runtime_token`. Devolve o aviso, se houver.
        """
        if self.s3a_resolver is None:
            return None
        resolution = self.s3a_resolver()
        self._s3a_options = resolution.options
        if self.runtime_grant is not None:
            self.runtime_grant = replace(self.runtime_grant, s3a_fingerprint=resolution.fingerprint)
        if self.local_catalog_factory is not None:
            self.catalog_ensure = self.local_catalog_factory(resolution.options)
        return resolution.notice

    async def _await_ready(self, client: AsyncKernelClient) -> None:
        try:
            await client.wait_for_ready(timeout=READY_TIMEOUT)
        except RuntimeError:
            await self._mark_dead()
            return
        except Exception:
            log.exception("kernel did not become ready for session %s", self.session_id)
            await self._mark_dead()
            return
        await self._install_display(client)
        if self.state in ("starting", "restarting") and not self.closing:
            await self.set_state("idle")

    async def _install_display(self, client: AsyncKernelClient) -> None:
        """Start the readers and install the DataFrame renderer and catalog hook with a silent execute.

        The reply is awaited briefly so a failure is logged, but a slow or
        failed install never blocks the kernel from becoming idle for long.
        """
        try:
            msg_id = client.execute(
                f"{build_ensure_code()}\n{self.catalog_ensure}" if self.catalog_ensure else build_ensure_code(),
                silent=True,
                store_history=False,
                user_expressions={"ok": ENSURE_CHECK},
                allow_stdin=False,
                stop_on_error=False,
            )
        except Exception:
            log.warning("display install not sent for session %s", self.session_id, exc_info=True)
            self._start_readers(client)
            return
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._probes[msg_id] = future
        self._start_readers(client)
        try:
            reply = await asyncio.wait_for(future, ENSURE_WAIT)
        except TimeoutError:
            log.warning("display install timed out for session %s", self.session_id)
            return
        finally:
            self._probes.pop(msg_id, None)
        status = reply.get("status")
        if status == "aborted":
            return
        check = (reply.get("user_expressions") or {}).get("ok") or {}
        if status != "ok" or check.get("data", {}).get("text/plain") != "True":
            log.warning("display install failed for session %s: %s", self.session_id, reply.get("ename") or status)

    async def _mark_dead(self) -> None:
        if self.closing or self._restarting:
            return
        await self._abort_pending()
        await self.set_state("dead")

    async def _abort_pending(self) -> None:
        probes, self._probes = self._probes, {}
        for future in probes.values():
            if not future.done():
                future.set_result({"status": "aborted"})
        pending, self.pending = self.pending, {}
        for item in pending.values():
            await self.emit(ExecuteReplyEvent(cell_id=item.cell_id, status="aborted"))

    async def _monitor(self) -> None:
        while not self.closing:
            await asyncio.sleep(LIVENESS_INTERVAL)
            if self._restarting or self.state == "dead" or self.closing:
                continue
            try:
                alive = await self.manager.is_alive()
            except Exception:
                log.debug("is_alive failed for %s", self.session_id, exc_info=True)
                alive = False
            if not alive:
                await self._mark_dead()

    async def _iopub_loop(self, client: AsyncKernelClient) -> None:
        while True:
            msg = await client.get_iopub_msg()
            msg_id = msg.get("parent_header", {}).get("msg_id")
            item = self.pending.get(msg_id) if msg_id else None
            if item is not None:
                await self._route_iopub(msg_id, item, msg)

    async def _route_iopub(self, msg_id: str, item: _Pending, msg: dict[str, Any]) -> None:
        msg_type = msg["header"]["msg_type"]
        content = msg["content"]
        cell_id = item.cell_id
        if msg_type == "status":
            if content["execution_state"] == "busy":
                await self.set_state("busy")
            elif content["execution_state"] == "idle":
                item.idle = True
                await self.set_state("idle")
                await self._maybe_finish(msg_id)
        elif msg_type == "execute_input":
            await self.emit(ExecuteInputEvent(cell_id=cell_id, execution_count=content.get("execution_count")))
        elif msg_type == "clear_output":
            self.stream_bytes.pop(cell_id, None)
            await self.emit(ClearOutputEvent(cell_id=cell_id, wait=bool(content.get("wait", False))))
        elif msg_type in ("stream", "display_data", "execute_result", "error"):
            output = self._to_output(cell_id, msg_type, msg)
            if output is not None:
                await self.emit(OutputEvent(cell_id=cell_id, output=output))

    def _to_output(self, cell_id: str, msg_type: str, msg: dict[str, Any]) -> dict[str, Any] | None:
        if msg_type == "stream":
            text = self._clip_stream(cell_id, msg["content"]["text"])
            if text is None:
                return None
            msg = {**msg, "content": {**msg["content"], "text": text}}
        return dict(output_from_msg(msg))

    def _clip_stream(self, cell_id: str, text: str) -> str | None:
        used = self.stream_bytes.get(cell_id, 0)
        if used > STREAM_LIMIT_BYTES:
            return None
        size = len(text.encode("utf-8", "replace"))
        if used + size <= STREAM_LIMIT_BYTES:
            self.stream_bytes[cell_id] = used + size
            return text
        room = STREAM_LIMIT_BYTES - used
        kept = text.encode("utf-8", "replace")[:room].decode("utf-8", "ignore")
        self.stream_bytes[cell_id] = STREAM_LIMIT_BYTES + 1
        return kept + TRUNCATION_NOTICE

    async def _shell_loop(self, client: AsyncKernelClient) -> None:
        while True:
            msg = await client.get_shell_msg()
            if msg["header"]["msg_type"] != "execute_reply":
                continue
            msg_id = msg.get("parent_header", {}).get("msg_id")
            probe = self._probes.get(msg_id) if msg_id else None
            if probe is not None:
                # Resposta do execute silencioso de `_install_display`: nunca chega ao WS nem a `pending`.
                if not probe.done():
                    probe.set_result(msg["content"])
                continue
            item = self.pending.get(msg_id) if msg_id else None
            if item is None:
                continue
            content = msg["content"]
            item.reply = ExecuteReplyEvent(
                cell_id=item.cell_id,
                status=content.get("status", "error"),
                execution_count=content.get("execution_count"),
            )
            # Aborted requests may never publish `idle`; waiting would hang the cell.
            if item.reply.status == "aborted":
                item.idle = True
            await self._maybe_finish(msg_id)
            if msg_id in self.pending:
                asyncio.get_running_loop().call_later(IDLE_GRACE, self._force_finish, msg_id)

    def _force_finish(self, msg_id: str) -> None:
        item = self.pending.get(msg_id)
        if item is not None:
            item.idle = True
            self._spawn(self._maybe_finish(msg_id))

    async def _maybe_finish(self, msg_id: str) -> None:
        item = self.pending.get(msg_id)
        if item is None or item.reply is None or not item.idle:
            return
        del self.pending[msg_id]
        self.stream_bytes.pop(item.cell_id, None)
        await self.emit(item.reply)

    async def execute(self, cell_id: str, code: str, language: Literal["python", "sql", "duckdb"] = "python") -> None:
        if self.blocked:
            await self.emit(ErrorEvent(code="catalog_busy", message="Catalog operation in progress; run again"))
            await self.emit(ExecuteReplyEvent(cell_id=cell_id, status="aborted"))
            return
        if self.state in ("starting", "dead", "restarting") or self.client is None:
            await self.emit(ErrorEvent(code=f"kernel_{self.state}", message=f"Kernel is {self.state}"))
            await self.emit(ExecuteReplyEvent(cell_id=cell_id, status="aborted"))
            return
        if language not in self.cell_languages:
            # Recusa no backend: o kernel pode não ser Python, então nenhum código é enviado a ele.
            message = _unavailable_message(language, self.kind, self.spec_language)
            error = {"output_type": "error", "ename": "RuntimeError", "evalue": message, "traceback": [message]}
            await self.emit(OutputEvent(cell_id=cell_id, output=error))
            await self.emit(ExecuteReplyEvent(cell_id=cell_id, status="error"))
            return
        self.stream_bytes[cell_id] = 0
        source = self._build_source(code, language)
        msg_id = self.client.execute(source, allow_stdin=False)
        self.pending[msg_id] = _Pending(cell_id=cell_id)

    def _build_source(self, code: str, language: str) -> str:
        if language == "sql":
            return build_sql_code(code)
        if language == "duckdb":
            if self.duckdb_kernel:
                return build_duckdb_kernel_code(code)
            # Extensões ficam sob a raiz única de dados; o autoinstall é desligado no kernel.
            return build_duckdb_code(code, self.duckdb_ext_dir)
        return code

    async def interrupt(self) -> None:
        if self.state in ("dead", "restarting"):
            await self.emit(ErrorEvent(code=f"kernel_{self.state}", message=f"Kernel is {self.state}"))
            return
        await self.manager.interrupt_kernel()

    async def restart(self) -> None:
        async with self._lock:
            if self.closing:
                return
            # A conexão é resolvida antes de derrubar o kernel: se falhar, recusa e o kernel atual segue vivo.
            try:
                notice = self.refresh_s3a()
            except NotislakeUnavailable as exc:
                await self.emit(ErrorEvent(code=NOTISLAKE_UNAVAILABLE_CODE, message=exc.message))
                return
            except settings_store.ConfigInvalid:
                await self.emit(ErrorEvent(code=CONFIG_INVALID_CODE, message=CONFIG_INVALID_MESSAGE))
                return
            except Exception as exc:  # noqa: BLE001 - qualquer falha da resolução recusa o restart sem derrubar o kernel
                log.warning("restart refused for session %s: cannot resolve the S3A connection (%s)", self.session_id, type(exc).__name__)
                await self.emit(ErrorEvent(code="restart_failed", message="Kernel restart failed"))
                return
            self._restarting = True
            try:
                await self.set_state("restarting")
                await self._abort_pending()
                await self._close_channels()
                self.issue_runtime_token()  # o kernel novo recebe um token novo; o do kernel antigo morre aqui
                await self.manager.restart_kernel(now=True)
                self._open_channels()
            except Exception:
                log.exception("restart failed for session %s", self.session_id)
                self._restarting = False
                await self._mark_dead()
                await self.emit(ErrorEvent(code="restart_failed", message="Kernel restart failed"))
                return
            self._restarting = False
            if notice is not None:
                log.warning("session %s restarted with S3A notice: %s", self.session_id, notice[0])
                await self.emit(ErrorEvent(code=notice[0], message=notice[1]))

    async def close(self) -> None:
        async with self._lock:
            self.closing = True
            self.sink = None
            if self.runtime_tokens is not None:
                self.runtime_tokens.revoke(self.session_id)
            for task in list(self._bg_tasks):
                task.cancel()
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
            await self._close_channels()
            try:
                await self.manager.shutdown_kernel(now=False)
            except Exception:
                log.warning("graceful shutdown failed for %s; killing", self.session_id, exc_info=True)
                with contextlib.suppress(Exception):
                    await self.manager.shutdown_kernel(now=True)
            await self._reap_docker_kernel()

    async def _reap_docker_kernel(self) -> None:
        """Mata o grupo do kernel no container: matar o `docker exec` local não encerra o que roda lá dentro."""
        runtime = self.docker_runtime
        if runtime is None:
            return
        try:
            await asyncio.wait_for(asyncio.to_thread(docker_launch.kill_kernel, runtime, self.docker_tag), DOCKER_KILL_WAIT)
        except (TimeoutError, docker_launch.LaunchError, docker_cli.DockerError, OSError) as exc:
            log.warning("kernel of session %s may still run in the container: %s", self.session_id, type(exc).__name__)


class KernelService:
    def __init__(self, port: int, runtime_dir: Path | None = None, home: Path | None = None) -> None:
        self._sessions: dict[str, KernelSession] = {}
        self._starting: dict[str, str] = {}  # session_id -> kernel_name while `start` is pending
        self._starting_paths: dict[str, Path | None] = {}  # session_id -> resolved target while `start` is pending
        self._reservations = 0
        self._docker: DockerRuntimes | None = None
        self._notislake: NotislakeSupervisor | None = None
        self._sweep_task: asyncio.Task[None] | None = None
        self.runtime_tokens = RuntimeTokens()
        self._port = port
        self._prefix = f"notisbook-{port}-"
        self._runtime_dir = runtime_dir or Path(jupyter_runtime_dir()) / "notisbook"
        self._home = Path(os.path.abspath((home or Settings().home).expanduser()))
        # Só a pasta `kernels` do home: kernels de terceiros ficam fora do app, na listagem e no launch.
        self._specs = KernelSpecManager(kernel_dirs=[str(kernels_dir(self._home))], ensure_native_kernel=False)
        self._duckdb_ext_dir = str((home or Settings().home) / "duckdb" / "extensions")
        self._catalog_db_path = str(catalog_db_path(self._home))

    def cleanup_orphans(self) -> int:
        """Remove connection files left by a previous run on the same port."""
        removed = 0
        if self._runtime_dir.is_dir():
            for entry in self._runtime_dir.glob(f"{self._prefix}*.json"):
                with contextlib.suppress(OSError):
                    entry.unlink()
                    removed += 1
        return removed

    def reconcile_kernelspecs(self) -> None:
        """Migra os specs legados da pasta global e remove os do home cujo interpretador sumiu; nunca levanta.

        Env inacessível (permissão) é deixado como está, com warning.
        """
        for step in (self._migrate_legacy_kernelspecs, self._migrate_legacy_docker, self._remove_orphan_kernelspecs):
            try:
                step()
            except Exception as exc:  # o startup não pode cair por causa da limpeza; o próximo boot tenta de novo
                log.warning("kernelspec reconciliation step %s failed: %s", step.__name__, type(exc).__name__)

    def _owned_specs(self, root: Path) -> list[tuple[Path, Path, PythonState]]:
        """`(spec_dir, env_dir, state)` dos specs Spark e DuckDB de `root` que apontam para este home."""
        found = [(d, e.env_dir, state) for d, e, state in spark_kernelspec.owned_specs(self._home, root)]
        found.extend((d, e.env_dir, state) for d, e, state in duckdb_kernelspec.owned_specs(self._home, root))
        return found

    def _migrate_legacy_kernelspecs(self) -> None:
        """Move para `<home>/kernels` os specs globais deste home com env instalado; os demais deste home são apagados.

        Um env gerenciado inutilizável vai para a lixeira antes de o spec ser apagado.

        Specs de outro home ou não reconhecidos não são tocados; o Docker global tem passo próprio.
        """
        target_root = kernels_dir(self._home)
        present = {d.name for d, _env, state in self._owned_specs(target_root) if state is PythonState.USABLE}
        for spec_dir, env_dir, state in self._owned_specs(legacy_kernels_dir()):
            name = spec_dir.name
            if state is PythonState.INACCESSIBLE:
                log.warning("kernelspec %s: env %s is not accessible, left untouched", name, env_dir.name)
                continue
            try:
                migrate = state is PythonState.USABLE and name not in present
                if migrate:
                    copy_kernel_json(spec_dir, target_root / name)
                elif state is PythonState.UNUSABLE and env_dir.is_dir() and self._is_managed_env(env_dir):
                    if not self._trash_env(env_dir):
                        log.warning("legacy kernelspec %s kept: env %s is unusable and could not be trashed", name, env_dir.name)
                        continue
                shutil.rmtree(spec_dir)
                log.info("%s legacy kernelspec %s", "migrated" if migrate else "removed", name)
            except OSError as exc:
                log.warning("cannot migrate legacy kernelspec %s: %s", name, type(exc).__name__)

    def _migrate_legacy_docker(self) -> None:
        """Move para o home o spec Docker global válido cujo `argv[0]` está sob este Python e que o home ainda não tem."""
        legacy_root = legacy_kernels_dir()
        for runtime in docker_catalog.CATALOG:
            source = legacy_root / runtime.kernel_name
            try:
                if not docker_spec.is_ours_at(source, runtime) or docker_spec.read_registration(self._home, runtime) is not None:
                    continue
                docker_spec.copy_registration(source, self._home, runtime)
                shutil.rmtree(source)
                log.info("migrated legacy kernelspec %s", runtime.kernel_name)
            except OSError as exc:
                log.warning("cannot migrate legacy kernelspec %s: %s", runtime.kernel_name, type(exc).__name__)

    def _remove_orphan_kernelspecs(self) -> None:
        """Remove os specs do home sem interpretador utilizável; um env que ainda existe vai para a lixeira.

        Env inacessível não é removido nem movido: pode ser um env bom, só bloqueado.
        """
        for spec_dir, env_dir, state in self._owned_specs(kernels_dir(self._home)):
            if state is PythonState.USABLE:
                continue
            if state is PythonState.INACCESSIBLE:
                log.warning("kernelspec %s: env %s is not accessible, left untouched", spec_dir.name, env_dir.name)
                continue
            try:
                env_present = env_dir.is_dir()
                if env_present and self._is_managed_env(env_dir) and not self._trash_env(env_dir):
                    log.warning("kernelspec %s kept: env %s is unusable and could not be trashed", spec_dir.name, env_dir.name)
                    continue
                shutil.rmtree(spec_dir)
                reason = "interpreter unusable, env moved to trash" if env_present else "env is missing"
                log.info("removed kernelspec %s: %s (%s)", spec_dir.name, reason, env_dir.name)
            except OSError as exc:
                log.warning("cannot remove kernelspec %s: %s", spec_dir.name, type(exc).__name__)

    def _is_managed_env(self, env_dir: Path) -> bool:
        return spark_kernelspec.is_managed_env(self._home, env_dir) or duckdb_kernelspec.is_managed_env(self._home, env_dir)

    def _trash_env(self, env_dir: Path) -> bool:
        """Renomeia o env para `.trash-<nome>` (o `sweep_trash` apaga); False se não conseguir."""
        doomed = env_dir.parent / f"{TRASH_PREFIX}{env_dir.name}"
        try:
            if doomed.exists():
                shutil.rmtree(doomed)
            os.rename(env_dir, doomed)
        except OSError:
            return False
        return True

    def _managed_kernel_names(self) -> set[str]:
        """Nomes dos kernels instalados pelo Notisbook: Spark e DuckDB gerenciados e Docker registrados."""
        names = {entry.kernel_name for entry in spark_kernelspec.discover(self._home)}
        names.update(entry.kernel_name for entry in duckdb_kernelspec.discover(self._home))
        names.update(
            runtime.kernel_name
            for runtime in docker_catalog.CATALOG
            if docker_spec.read_registration(self._home, runtime) is not None
        )
        return names

    def _list_managed_specs(self) -> dict[str, Any]:
        managed = self._managed_kernel_names()
        return {name: info for name, info in self._specs.get_all_specs().items() if name in managed}

    async def kernelspecs(self) -> list[KernelSpecInfo]:
        """Só os kernels instalados pelo Notisbook; kernels de terceiros da máquina não são listados."""
        specs = await asyncio.to_thread(self._list_managed_specs)
        result: list[KernelSpecInfo] = []
        for name, info in specs.items():
            spec = info["spec"]
            language = spec.get("language", "")
            metadata = spec.get("metadata")
            kind = runtime_kind(name, metadata)
            result.append(
                {
                    "name": name,
                    "display_name": spec.get("display_name", name),
                    "language": language,
                    "cell_languages": list(cell_languages_for(kind, language)),
                    "runtime_kind": kind,
                }
            )
        # Docker por último: o frontend usa o primeiro item como padrão e o Spark Local não pode mudar.
        return sorted(result, key=lambda item: (item["name"].startswith(DOCKER_KERNEL_PREFIX), item["name"]))

    def bind_docker(self, docker: DockerRuntimes) -> None:
        """Liga o serviço dos runtimes Docker (criado depois deste, pois recebe `has_session`)."""
        self._docker = docker

    def bind_notislake(self, notislake: NotislakeSupervisor | None) -> None:
        """Liga o supervisor do MinIO; sem ele (testes, uso embutido) `create` não consulta o estado."""
        self._notislake = notislake

    def start_docker_sweep(self) -> None:
        """Agenda a varredura de kernels órfãos nos containers do app; sessões Docker esperam por ela."""
        if self._docker is not None:
            self._sweep_task = asyncio.ensure_future(self._sweep_docker_orphans())

    async def _sweep_docker_orphans(self) -> None:
        try:
            await asyncio.wait_for(self._sweep_running_containers(), DOCKER_SWEEP_WAIT)
        except (TimeoutError, docker_cli.DockerError, docker_launch.LaunchError, OSError) as exc:  # Docker fora do ar não impede o app de subir
            log.warning("orphan kernel sweep skipped: %s", type(exc).__name__)

    async def _sweep_running_containers(self) -> None:
        if not await asyncio.to_thread(docker_cli.is_available):
            return
        for runtime in docker_catalog.CATALOG:
            info = await asyncio.to_thread(inspect_container, runtime)
            if info is None or not info.running or not info.owned_by(runtime):
                continue
            killed = await asyncio.to_thread(docker_launch.sweep, runtime)
            if killed:
                log.info("swept %d orphan kernel(s) in container of runtime %s", killed, runtime.key)

    async def stop_docker_runtimes(self) -> None:
        """No encerramento do app: para (sem remover) os containers do app; falhas não travam o shutdown."""
        task, self._sweep_task = self._sweep_task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        docker = self._docker
        if docker is None:
            return
        for runtime in docker_catalog.CATALOG:
            try:
                await asyncio.wait_for(docker.stop(runtime), DOCKER_STOP_WAIT)
            except DOCKER_STOP_SKIPPED as exc:  # container ausente, Docker fora do ar, timeout: nada a parar
                log.warning("container %s was not stopped at shutdown: %s", runtime.container, type(exc).__name__)

    async def _prepare_docker(self, runtime: docker_catalog.DockerRuntime) -> MountPlan:
        """Garante que o runtime Docker pode abrir um kernel e deixa o container rodando; levanta `DockerRuntimeError`.

        Devolve o plano de montagens validado, de onde saem as pastas que o token de runtime da sessão alcança.
        """
        docker = self._docker
        if docker is None:
            raise DockerRuntimeError(503, "Runtime Docker indisponível neste servidor")
        sweep = self._sweep_task
        if sweep is not None and not sweep.done():
            await asyncio.shield(sweep)
        if not await asyncio.to_thread(docker_cli.is_available):
            raise DockerRuntimeError(503, "Docker indisponível: inicie o Colima (ou o daemon Docker) e tente de novo")
        info = await self._inspect_docker(runtime)
        plan = await self._check_docker_mounts(docker, info)
        self._refuse_if_mutating(docker, runtime)
        if not info.running:
            try:
                await asyncio.to_thread(docker_launch.ensure_started, runtime)
            except (docker_launch.LaunchError, docker_cli.DockerError) as exc:
                raise DockerRuntimeError(503, f"Não foi possível iniciar o container do runtime Docker: {exc}") from exc
        await asyncio.to_thread(self._refresh_docker_spec, runtime)
        return plan

    def _resolve_s3a(self, *, docker: bool) -> S3AResolution:
        """Resolve a conexão S3A (`objectstore.resolve`) e gera as opções do kernel, local ou Docker.

        Abertura e restart usam a mesma regra, que falha fechada: manual inválido levanta `ConfigInvalid`;
        automático sem MinIO `running` levanta `NotislakeUnavailable`. Sem supervisor (testes, uso embutido)
        devolve a resolução vazia.
        """
        supervisor = self._notislake
        try:
            conn = objectstore.resolve_from_app(self._home, supervisor)
        except objectstore.Unavailable:
            if supervisor is None:
                return S3AResolution()
            raise NotislakeUnavailable(supervisor.snapshot().state.value) from None
        notice: tuple[str, str] | None = None
        if docker and conn.source == "manual":
            parts = urlsplit(conn.endpoint)
            if parts.scheme == "https" and parts.hostname and settings_store.is_loopback_host(parts.hostname):
                notice = S3A_LOOPBACK_HTTPS_NOTICE
                log.warning("manual notislake endpoint is https on loopback: not supported in the Docker runtime")
        return S3AResolution(dict(s3a_options(conn, docker=docker)), fingerprint(conn), notice)

    def _duckdb_bootstrap_factory(self, spec: Any) -> Callable[[str, Mapping[str, str] | None], str]:
        """Bootstrap do kernel DuckDB; o diretório e a lista de extensões vêm do metadata do kernelspec."""
        meta = spec.metadata[DUCKDB_METADATA_KEY]
        ext_dir = str(meta.get("extension_directory") or "")
        extensions = tuple(str(e) for e in meta.get("extensions") or ())
        port = self._port

        def build(token: str, s3a: Mapping[str, str] | None) -> str:
            return build_duckdb_bootstrap_code(ext_dir, extensions, s3a, port, token)

        return build

    def _local_catalog_factory(self) -> Callable[[Mapping[str, str] | None], str]:
        """Snippet do hook com transporte SQLite; as opções S3A entram por sessão."""
        db_path = self._catalog_db_path

        def build(s3a: Mapping[str, str] | None) -> str:
            return build_catalog_ensure_code(db_path, s3a=s3a)

        return build

    def _runtime_grant(
        self, session_id: str, plan: MountPlan, s3a_fingerprint: str | None = None, *, glue: bool = False
    ) -> RuntimeGrant:
        """Raízes locais do token: todas as montagens do plano (por realpath), Connections inclusive quando montada."""
        roots = tuple(dict.fromkeys(os.path.realpath(p) for p in plan.paths))
        return RuntimeGrant(
            session_id=session_id,
            roots=roots,
            s3a_fingerprint=s3a_fingerprint,
            glue=glue,
        )

    def _docker_catalog_factory(
        self, grant: RuntimeGrant, *, glue: bool = False
    ) -> Callable[[str, Mapping[str, str] | None], str]:
        """Snippet do hook com transporte HTTP; o container alcança o backend pelo `host.lima.internal`.

        No runtime Glue o snippet leva o id da sessão (access key do endpoint Glue); o segredo é o token de cada kernel.
        """
        base_url = f"http://{RUNTIME_HOST}:{self._port}/api/runtime-catalog"
        access_key = grant.session_id if glue else None

        def build(token: str, s3a: Mapping[str, str] | None) -> str:
            return build_catalog_http_ensure_code(base_url, token, grant.roots, s3a=s3a, glue_access_key=access_key)

        return build

    @staticmethod
    def _refuse_if_mutating(docker: DockerRuntimes, runtime: docker_catalog.DockerRuntime) -> None:
        if docker.is_mutating(runtime.kernel_name):
            raise DockerRuntimeError(
                409, "O runtime Docker está sendo instalado, recriado ou alterado; tente de novo quando a operação terminar"
            )

    @staticmethod
    async def _inspect_docker(runtime: docker_catalog.DockerRuntime) -> ContainerInfo:
        try:
            info = await asyncio.to_thread(inspect_container, runtime)
        except docker_cli.DockerError as exc:
            raise DockerRuntimeError(503, "Docker não respondeu ao consultar o container do runtime") from exc
        if info is None:
            raise DockerRuntimeError(
                409,
                f"O container {runtime.container} não existe: use Recriar no runtime Docker (Settings › Runtimes)",
            )
        if not info.owned_by(runtime):
            raise DockerRuntimeError(409, f"O container {runtime.container} não pertence ao Notisbook; ele não foi alterado")
        return info

    @staticmethod
    async def _check_docker_mounts(docker: DockerRuntimes, info: ContainerInfo) -> MountPlan:
        try:
            plan = await asyncio.to_thread(docker.plan_mounts, None)
        except MountRejected as exc:
            raise DockerRuntimeError(409, f"A pasta atual não serve ao runtime Docker ({exc.field}): {exc.message}") from exc
        except OSError as exc:
            raise DockerRuntimeError(503, "Não foi possível preparar a pasta warehouse do runtime Docker") from exc
        required = {str(plan.notebooks), str(plan.warehouse)}
        if required - set(info.mounts):
            raise DockerRuntimeError(
                409,
                "As pastas montadas no container estão defasadas em relação à raiz atual dos notebooks; "
                "use Recriar no runtime Docker (Settings › Runtimes) e tente de novo",
            )
        # A Connections é escolha do cliente: o backend a descobre pela montagem real do container, revalidada.
        for source in sorted(set(info.mounts) - required):
            try:
                connections = (await asyncio.to_thread(docker.plan_mounts, source)).connections
            except (MountRejected, OSError):
                continue
            if connections is not None:
                return replace(plan, connections=connections)
        return plan

    def _refresh_docker_spec(self, runtime: docker_catalog.DockerRuntime) -> None:
        """Regrava o kernelspec se o `argv[0]` não for o Python deste app (ex.: venv recriada)."""
        spec = self._specs.get_kernel_spec(runtime.kernel_name)
        if not spec.argv or spec.argv[0] != sys.executable:
            docker_spec.write_kernelspec(self._home, runtime)

    def _ensure_log4j2(self, spec: Any) -> None:
        """Keep the log4j2 config of a Notisbook-managed Spark env current; never blocks the start."""
        try:
            managed = isinstance(spec.metadata, dict) and METADATA_KEY in spec.metadata
            conf = Path(spec.env.get("SPARK_CONF_DIR", ""))
            if managed and conf.name == "spark-conf" and is_managed_env(self._home, Path(os.path.abspath(conf.parent))):
                write_log4j2(conf)
        except Exception:
            log.warning("cannot ensure log4j2.properties for kernel %s", getattr(spec, "display_name", "?"), exc_info=True)

    def _ensure_spark_defaults(self, spec: Any) -> None:
        """Re-render `spark-defaults.conf` from the current matrix, only when every jar it names is installed.

        The kernel is offline, so nothing is downloaded here. A managed env without a current S3A record (or
        missing any jar the conf names, formats bundle included) has no S3A config to run on: raises `SparkEnvOutdated`.
        The bundle is optional: an env without it runs S3A only.
        So does a conf that cannot be rewritten (unsupported home, write error), unless the current one already
        points `spark.sql.warehouse.dir` at the local safety warehouse. That fallback only applies once the env is
        confirmed as a managed Spark env; any other failure is logged and never blocks the start.
        """
        confirmed = False
        try:
            managed = isinstance(spec.metadata, dict) and METADATA_KEY in spec.metadata
            conf = Path(spec.env.get("SPARK_CONF_DIR", ""))
            env_dir = Path(os.path.abspath(conf.parent))
            if not (managed and conf.name == "spark-conf" and is_managed_env(self._home, env_dir)):
                return
            confirmed = True
            meta = spec.metadata[METADATA_KEY]
            version = meta.get("version")
            status, s3a, shared = s3a_plan(env_dir, version, meta) if isinstance(version, str) else ("outdated", None, False)
            if s3a is None:
                log.warning("spark env %s has no current S3A jars (%s); reinstall the Spark version", env_dir.name, status)
                raise SparkEnvOutdated
            bundle = bundle_for(version) if isinstance(meta.get("bundle"), dict) else None
            resolve = JarCache(self._home).path if shared else (lambda artifact: jars_dir(env_dir) / artifact.filename)
            needed = (*(bundle.artifacts if bundle else ()), *(bundle.driver_artifacts if bundle else ()), *s3a.artifacts)
            missing = [a.filename for a in needed if not resolve(a).is_file()]
            if missing:
                log.warning("spark env %s is outdated: missing %s; reinstall the Spark version", env_dir.name, ", ".join(missing))
                raise SparkEnvOutdated
            if write_spark_defaults(conf, render_spark_defaults(bundle, s3a, resolve, self._home)):
                log.info("spark-defaults.conf of %s updated", env_dir.name)
        except SparkEnvOutdated:
            raise
        except UnsupportedHome as exc:
            log.warning("spark-defaults.conf of kernel %s not updated: %s", getattr(spec, "display_name", "?"), exc)
            if confirmed:
                self._require_safety_warehouse(spec)
        except Exception:
            log.warning("cannot ensure spark-defaults.conf for kernel %s", getattr(spec, "display_name", "?"), exc_info=True)
            if confirmed:
                self._require_safety_warehouse(spec)

    def _require_safety_warehouse(self, spec: Any) -> None:
        """Fail closed: the stale conf is only usable when it already names the local safety warehouse."""
        try:
            lines = (Path(spec.env["SPARK_CONF_DIR"]) / "spark-defaults.conf").read_text(encoding="utf-8").splitlines()
        except (KeyError, OSError, UnicodeDecodeError):
            raise SparkEnvOutdated from None
        pairs = (line.split(None, 1) for line in lines)
        values = [pair[1].strip() for pair in pairs if len(pair) == 2 and pair[0] == "spark.sql.warehouse.dir"]
        if not values or values[-1] != safety_warehouse_uri(self._home):  # the last duplicate wins in a properties file
            raise SparkEnvOutdated

    @staticmethod
    def _unmanaged_error(kernel_name: str) -> Exception:
        """Nome com nomenclatura do Notisbook sem runtime instalado é `RuntimeNotInstalled`; qualquer outro, `KernelNotFound`."""
        notisbook_name = (
            is_spark_kernel_name(kernel_name)
            or is_duckdb_kernel_name(kernel_name)
            or docker_catalog.by_kernel_name(kernel_name) is not None
        )
        return RuntimeNotInstalled(kernel_name) if notisbook_name else KernelNotFound(kernel_name)

    @staticmethod
    def _interpreter_ready(spec: Any) -> bool:
        argv = getattr(spec, "argv", None)
        return bool(argv) and python_usable(Path(os.path.abspath(argv[0])))

    def resolve_kernel_name(self, kernel_name: str) -> str:
        """Resolve the alias `duckdb` using only managed kernelspecs (third-party ones are ignored).

        Sync on purpose (a directory listing): callers resolve and register the session with no await between.
        A managed legacy `duckdb` wins; otherwise the newest managed `duckdb-*`. Any other name, or an alias
        with nothing managed installed, is returned unchanged.
        """
        if kernel_name != DUCKDB_KERNEL_NAME:
            return kernel_name
        # `discover` só devolve kernelspecs cujo ambiente é gerenciado e já vem do mais novo ao mais antigo.
        managed = duckdb_kernelspec.discover(self._home)
        if not managed:
            return kernel_name
        if any(spec.kernel_name == DUCKDB_KERNEL_NAME for spec in managed):
            return DUCKDB_KERNEL_NAME
        return managed[0].kernel_name

    async def create(
        self, path: str, kernel_name: str, cwd: Path | None = None, target: Path | None = None
    ) -> KernelSession:
        """Cria a sessão. O registro em `_starting*` é síncrono (sem await antes), o que o torna atômico no event loop.

        Levanta `ConfigInvalid` (conexão manual inválida) ou `NotislakeUnavailable` (automático sem MinIO `running`);
        só sessões novas são recusadas. Uma conexão manual válida abre mesmo com o MinIO local fora.
        """
        # Antes de registrar em `_starting`, para `has_session` enxergar o nome real do kernel.
        kernel_name = self.resolve_kernel_name(kernel_name)
        # Sem o metadata do kernelspec (só chega após o await) o DuckDB não é visível; docker e local já se decidem aqui.
        docker_runtime = docker_catalog.by_kernel_name(kernel_name)
        is_docker = docker_runtime is not None
        s3a = self._resolve_s3a(docker=is_docker)
        session_id = uuid.uuid4().hex
        # Registered before the spec lookup so has_session sees the session during the whole arranque.
        self._starting[session_id] = kernel_name
        self._starting_paths[session_id] = target
        try:
            if docker_runtime is None and kernel_name.startswith(DOCKER_KERNEL_PREFIX):
                raise KernelNotFound(kernel_name)
            if docker_runtime is not None and self._docker is not None:
                # Antes de qualquer await: a recusa vale para o instante em que a requisição chegou.
                self._refuse_if_mutating(self._docker, docker_runtime)
            # Sem await desde o registro: kernel de terceiros é recusado como um kernel inexistente.
            if kernel_name not in self._managed_kernel_names():
                raise self._unmanaged_error(kernel_name)
            try:
                spec = await asyncio.to_thread(self._specs.get_kernel_spec, kernel_name)
            except NoSuchKernel as exc:
                raise KernelNotFound(kernel_name) from exc
            if docker_runtime is None and not self._interpreter_ready(spec):
                raise RuntimeNotInstalled(kernel_name)
            runtime_grant: RuntimeGrant | None = None
            spec_metadata = getattr(spec, "metadata", None)
            kind = runtime_kind(kernel_name, spec_metadata, docker=is_docker)
            is_duckdb = kind == "duckdb"
            spec_language = str(getattr(spec, "language", ""))
            if is_duckdb:
                # O DuckDB só usa s3a (sem pastas locais): roots vazio; o fingerprint libera a gravação em s3a.
                runtime_grant = RuntimeGrant(session_id=session_id, roots=(), s3a_fingerprint=s3a.fingerprint)
            elif docker_runtime is not None:
                runtime_grant = self._runtime_grant(
                    session_id,
                    await self._prepare_docker(docker_runtime),
                    s3a.fingerprint,
                    glue=docker_runtime.key == "glue",
                )
            else:
                await asyncio.to_thread(self._ensure_log4j2, spec)
                await asyncio.to_thread(self._ensure_spark_defaults, spec)
            self._runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            connection_file = str(self._runtime_dir / f"{self._prefix}{session_id}.json")
            manager = AsyncKernelManager(
                kernel_name=kernel_name, connection_file=connection_file, kernel_spec_manager=self._specs
            )
            manager.shutdown_wait_time = SHUTDOWN_WAIT
            local_factory = None if is_duckdb else self._local_catalog_factory()
            catalog_factory = None
            if is_duckdb:
                catalog_factory = self._duckdb_bootstrap_factory(spec)
            elif docker_runtime is not None and runtime_grant is not None:
                catalog_factory = self._docker_catalog_factory(runtime_grant, glue=docker_runtime.key == "glue")
            session = KernelSession(
                session_id,
                path,
                kernel_name,
                manager,
                target=target,
                duckdb_ext_dir=self._duckdb_ext_dir,
                # O container nunca toca o catalog.db: no Docker o hook fala com a API do backend (snippet vem do token).
                catalog_ensure="" if (docker_runtime is not None or local_factory is None) else local_factory(s3a.options),
                catalog_factory=catalog_factory,
                local_catalog_factory=None if (docker_runtime is not None or is_duckdb) else local_factory,
                duckdb_kernel=is_duckdb,
                kind=kind,
                spec_language=spec_language,
                cell_languages=cell_languages_for(kind, spec_language),
                s3a_resolver=lambda: self._resolve_s3a(docker=is_docker),
                _s3a_options=s3a.options,
                s3a_notice=s3a.notice,
                docker_runtime=docker_runtime,
                docker_tag=docker_launch.tag_for(connection_file) if docker_runtime is not None else "",
                runtime_tokens=self.runtime_tokens if (docker_runtime is not None or is_duckdb) else None,
                runtime_grant=runtime_grant,
            )
            session.issue_runtime_token()
            env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
            if docker_runtime is not None:
                env[docker_launch.PORT_ENV] = str(self._port)
                env[docker_launch.HOME_ENV] = str(self._home)
            try:
                await session.start(env, cwd)
            except Exception:
                await session.close()
                raise
            else:
                session.blocked = self._reservations > 0
                self._sessions[session_id] = session
        finally:
            self._starting.pop(session_id, None)
            self._starting_paths.pop(session_id, None)
        return session

    def has_any_session(self) -> bool:
        """True when any session is active or still starting."""
        return bool(self._sessions or self._starting)

    def has_busy_session(self) -> bool:
        """True quando algum kernel executa uma célula ou tem uma já enviada e ainda sem resposta."""
        return any(s.state == "busy" or s.pending for s in self._sessions.values())

    @contextlib.contextmanager
    def reserve_idle(self) -> Iterator[None]:
        """Recusa novas células enquanto durar o bloco; levanta `KernelsBusy` se algum kernel já executa.

        Deve ser aberto no event loop: a checagem e o bloqueio acontecem sem `await` entre eles. Janela que
        resta: thread ou processo que uma célula anterior deixou rodando em segundo plano não é visto aqui.
        """
        if self.has_busy_session():
            raise KernelsBusy
        self._reservations += 1
        self._set_blocked(True)
        try:
            yield
        finally:
            self._reservations -= 1
            self._set_blocked(self._reservations > 0)

    def _set_blocked(self, value: bool) -> None:
        for session in self._sessions.values():
            session.blocked = value

    def has_session_under(self, targets: Iterable[Path]) -> bool:
        """True quando uma sessão (ativa ou iniciando) aponta para algum `targets` ou para algo dentro dele.

        Tudo em caminhos absolutos resolvidos, então um alias (symlink) não escapa da checagem.
        Deve rodar no event loop: `_sessions`/`_starting_paths` mudam nele.
        """
        wanted = list(targets)
        opened = [s.target for s in self._sessions.values()] + list(self._starting_paths.values())
        return any(t is not None and self._covers(w, t) for t in opened for w in wanted)

    @staticmethod
    def _covers(wanted: Path, opened: Path) -> bool:
        """True quando `opened` é `wanted` ou está dentro dele, inclusive só por diferença de caixa.

        `resolve()` não normaliza a caixa em FS case-insensitive (APFS); `samefile` confirma que o
        prefixo é o mesmo arquivo, sem bloquear nomes que só diferem em caixa num FS sensível a ela.
        """
        if opened == wanted or opened.is_relative_to(wanted):
            return True
        if not Path(str(opened).casefold()).is_relative_to(Path(str(wanted).casefold())):
            return False
        try:
            return os.path.samefile(Path(*opened.parts[: len(wanted.parts)]), wanted)
        except OSError:
            return False

    def has_session(self, kernel_name: str) -> bool:
        """True when a session of this kernel is active or still starting."""
        return kernel_name in self._starting.values() or any(
            s.kernel_name == kernel_name for s in self._sessions.values()
        )

    def get(self, session_id: str) -> KernelSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFound(session_id) from None

    def sessions(self) -> list[dict[str, str]]:
        return [s.info() for s in self._sessions.values()]

    async def delete(self, session_id: str) -> None:
        session = self.get(session_id)
        del self._sessions[session_id]
        await session.close()

    async def shutdown_all(self) -> None:
        sessions, self._sessions = list(self._sessions.values()), {}
        await asyncio.gather(*(s.close() for s in sessions), return_exceptions=True)
