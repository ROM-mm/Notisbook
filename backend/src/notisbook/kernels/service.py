"""Kernel sessions on top of `jupyter_client`.

This is the only module that imports `jupyter_client`, so the backend can be
swapped for `jupyter_server` without touching the API or the WS protocol.
"""

import asyncio
import contextlib
import logging
import os
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from jupyter_client.asynchronous.client import AsyncKernelClient
from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel
from jupyter_client.manager import AsyncKernelManager
from jupyter_core.paths import jupyter_runtime_dir
from nbformat.v4 import output_from_msg

from ..catalog.store import catalog_db_path
from ..config import Settings
from ..spark.bundles import (
    SPARK_WAREHOUSE_SUBDIR,
    WAREHOUSE_DIR,
    UnsupportedHome,
    bundle_for,
    render_spark_defaults,
    write_log4j2,
    write_spark_defaults,
)
from ..spark.kernelspec import METADATA_KEY, is_managed_env, jars_dir
from .catalog_hook import build_ensure_code as build_catalog_ensure_code
from .introspect import Probe, VarOp, build_variables_request, parse_reply
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
from .sql_cell import build_code as build_sql_code
from .sql_cell import MODULE_NAME, build_duckdb_code, build_ensure_code

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
PROBE_WAIT = 1.5
ENSURE_WAIT = 3.0
ENSURE_CHECK = f"__import__('sys').modules.get({MODULE_NAME!r}) is not None"
MAX_CACHE = 100
TRUNCATION_NOTICE = "\n[output truncated: 1 MB limit per cell reached]\n"

Sink = Callable[[ServerEvent], Awaitable[None]]


class KernelNotFound(Exception):
    """No kernelspec with the requested name."""


class KernelsBusy(Exception):
    """Há célula em execução; a operação que exige os kernels ociosos foi recusada."""


class SessionNotFound(Exception):
    """No session with the requested id."""


@dataclass
class _Pending:
    cell_id: str
    reply: ExecuteReplyEvent | None = None
    idle: bool = False


@dataclass(frozen=True)
class Snapshot:
    """Variables probe answer: `status` is a Probe status, `busy` or `kernel_<state>`."""

    status: str
    data: Any = None
    stale: bool = False
    message: str | None = None


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
    catalog_ensure: str = ""
    _restarting: bool = False
    _channel_tasks: list[asyncio.Task[None]] = field(default_factory=list)
    _ready_task: asyncio.Task[None] | None = None
    _bg_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    _probes: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    # Faixa própria das variáveis: uma sonda por vez, cache próprio.
    _var_task: asyncio.Task[Probe] | None = None
    _var_key: str | None = None
    _var_cache: OrderedDict[str, Any] = field(default_factory=OrderedDict)
    _var_gen: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

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
                # Internal introspection reply: never reaches the WS or `pending`.
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
        self.stream_bytes[cell_id] = 0
        source = self._build_source(code, language)
        msg_id = self.client.execute(source, allow_stdin=False)
        self.pending[msg_id] = _Pending(cell_id=cell_id)

    def _build_source(self, code: str, language: str) -> str:
        if language == "sql":
            return build_sql_code(code)
        if language == "duckdb":
            # Extensões ficam sob a raiz única de dados; o autoinstall é desligado no kernel.
            return build_duckdb_code(code, self.duckdb_ext_dir)
        return code

    async def _send_probe(self, client: AsyncKernelClient, code: str, expressions: dict[str, str]) -> Probe:
        msg_id = client.execute(
            code,
            silent=True,
            store_history=False,
            user_expressions=expressions,
            allow_stdin=False,
            stop_on_error=False,
        )
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._probes[msg_id] = future
        try:
            return parse_reply(await future)
        finally:
            self._probes.pop(msg_id, None)

    async def introspect_variables(self, key: str, op: VarOp, args: dict[str, Any]) -> Snapshot:
        """Variables probe (one in flight, own cache).

        Kernel busy or probe slower than PROBE_WAIT: cached value marked `stale`, or
        `busy` + stale with no data. A path that no longer resolves is `stale_path`.
        """
        if self.state not in ("idle", "busy") or self.client is None:
            return Snapshot(f"kernel_{self.state}")
        if self.state == "busy" or self.pending:
            return self._var_from_cache(key)
        task = self._var_task
        if task is not None and self._var_key != key:
            return self._var_from_cache(key)
        if task is None:
            task = asyncio.ensure_future(self._run_var_probe(key, op, args))
            self._bg_tasks.add(task)
            self._var_task, self._var_key = task, key
            task.add_done_callback(self._bg_tasks.discard)
            task.add_done_callback(self._var_done)
        try:
            probe = await asyncio.wait_for(asyncio.shield(task), PROBE_WAIT)
        except TimeoutError:
            return self._var_from_cache(key)
        if probe.status == "ok":
            return Snapshot("ok", probe.data)
        if probe.status == "error":
            return Snapshot("error", self._var_cache.get(key), stale=key in self._var_cache, message=probe.message)
        return Snapshot(probe.status)

    def _var_done(self, task: asyncio.Task[Probe]) -> None:
        if self._var_task is task:
            self._var_task, self._var_key = None, None

    def _var_from_cache(self, key: str) -> Snapshot:
        if key in self._var_cache:
            self._var_cache.move_to_end(key)
            return Snapshot("ok", self._var_cache[key], stale=True)
        return Snapshot("busy", stale=True)

    async def _run_var_probe(self, key: str, op: VarOp, args: dict[str, Any]) -> Probe:
        client = self.client
        if client is None:
            return Probe("error", message="kernel has no client")
        generation = self._var_gen
        probe = await self._send_probe(client, *build_variables_request(op, args))
        # Um restart durante a sonda invalida a resposta: não repovoa o cache limpo.
        if probe.status == "ok" and generation == self._var_gen:
            self._var_cache[key] = probe.data
            self._var_cache.move_to_end(key)
            while len(self._var_cache) > MAX_CACHE:
                self._var_cache.popitem(last=False)
        return probe

    async def interrupt(self) -> None:
        if self.state in ("dead", "restarting"):
            await self.emit(ErrorEvent(code=f"kernel_{self.state}", message=f"Kernel is {self.state}"))
            return
        await self.manager.interrupt_kernel()

    async def restart(self) -> None:
        async with self._lock:
            if self.closing:
                return
            self._restarting = True
            try:
                await self.set_state("restarting")
                await self._abort_pending()
                await self._close_channels()
                self._var_cache.clear()
                self._var_gen += 1
                await self.manager.restart_kernel(now=True)
                self._open_channels()
            except Exception:
                log.exception("restart failed for session %s", self.session_id)
                self._restarting = False
                await self._mark_dead()
                await self.emit(ErrorEvent(code="restart_failed", message="Kernel restart failed"))
                return
            self._restarting = False

    async def close(self) -> None:
        async with self._lock:
            self.closing = True
            self.sink = None
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


class KernelService:
    def __init__(self, port: int, runtime_dir: Path | None = None, home: Path | None = None) -> None:
        self._specs = KernelSpecManager()
        self._sessions: dict[str, KernelSession] = {}
        self._starting: dict[str, str] = {}  # session_id -> kernel_name while `start` is pending
        self._starting_paths: dict[str, Path | None] = {}  # session_id -> resolved target while `start` is pending
        self._reservations = 0
        self._prefix = f"notisbook-{port}-"
        self._runtime_dir = runtime_dir or Path(jupyter_runtime_dir()) / "notisbook"
        self._home = Path(os.path.abspath((home or Settings().home).expanduser()))
        self._duckdb_ext_dir = str((home or Settings().home) / "duckdb" / "extensions")
        self._catalog_ensure = build_catalog_ensure_code(
            str(catalog_db_path(self._home)),
            str(self._home / WAREHOUSE_DIR / SPARK_WAREHOUSE_SUBDIR),
            str(self._home / WAREHOUSE_DIR / "iceberg"),
        )

    def cleanup_orphans(self) -> int:
        """Remove connection files left by a previous run on the same port."""
        removed = 0
        if self._runtime_dir.is_dir():
            for entry in self._runtime_dir.glob(f"{self._prefix}*.json"):
                with contextlib.suppress(OSError):
                    entry.unlink()
                    removed += 1
        return removed

    async def kernelspecs(self) -> list[dict[str, str]]:
        specs = await asyncio.to_thread(self._specs.get_all_specs)
        result = [
            {
                "name": name,
                "display_name": info["spec"].get("display_name", name),
                "language": info["spec"].get("language", ""),
            }
            for name, info in specs.items()
        ]
        return sorted(result, key=lambda item: item["name"])

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

        An env installed before a matrix revision keeps its conf until reinstalled if a jar is
        missing (the kernel is offline, so nothing is downloaded here). Never blocks the start.
        """
        try:
            managed = isinstance(spec.metadata, dict) and METADATA_KEY in spec.metadata
            conf = Path(spec.env.get("SPARK_CONF_DIR", ""))
            env_dir = Path(os.path.abspath(conf.parent))
            if not (managed and conf.name == "spark-conf" and is_managed_env(self._home, env_dir)):
                return
            version = spec.metadata[METADATA_KEY].get("version")
            bundle = bundle_for(version) if isinstance(version, str) else None
            if bundle is None:
                return
            jars = jars_dir(env_dir)
            missing = [a.filename for a in (*bundle.artifacts, *bundle.driver_artifacts) if not (jars / a.filename).is_file()]
            if missing:
                log.info("spark-defaults.conf of %s left as is: missing %s; reinstall the Spark version", env_dir.name, ", ".join(missing))
                return
            if write_spark_defaults(conf, render_spark_defaults(bundle, jars, self._home)):
                log.info("spark-defaults.conf of %s updated to bundle r%d", env_dir.name, bundle.revision)
        except UnsupportedHome as exc:
            log.warning("spark-defaults.conf of kernel %s not updated: %s", getattr(spec, "display_name", "?"), exc)
        except Exception:
            log.warning("cannot ensure spark-defaults.conf for kernel %s", getattr(spec, "display_name", "?"), exc_info=True)

    async def create(
        self, path: str, kernel_name: str, cwd: Path | None = None, target: Path | None = None
    ) -> KernelSession:
        """Cria a sessão. O registro em `_starting*` é síncrono (sem await antes), o que o torna atômico no event loop."""
        session_id = uuid.uuid4().hex
        # Registered before the spec lookup so has_session sees the session during the whole arranque.
        self._starting[session_id] = kernel_name
        self._starting_paths[session_id] = target
        try:
            try:
                spec = await asyncio.to_thread(self._specs.get_kernel_spec, kernel_name)
            except NoSuchKernel as exc:
                raise KernelNotFound(kernel_name) from exc
            await asyncio.to_thread(self._ensure_log4j2, spec)
            await asyncio.to_thread(self._ensure_spark_defaults, spec)
            self._runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            manager = AsyncKernelManager(
                kernel_name=kernel_name,
                connection_file=str(self._runtime_dir / f"{self._prefix}{session_id}.json"),
            )
            manager.shutdown_wait_time = SHUTDOWN_WAIT
            session = KernelSession(
                session_id,
                path,
                kernel_name,
                manager,
                target=target,
                duckdb_ext_dir=self._duckdb_ext_dir,
                catalog_ensure=self._catalog_ensure,
            )
            env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
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
