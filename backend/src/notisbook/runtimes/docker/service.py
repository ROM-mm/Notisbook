"""Instalação, recriação e controle dos runtimes Docker (container persistente compartilhado).

O app é o único dono do container: ele é marcado com labels de dono e qualquer container de mesmo
nome sem essas labels é tratado como alheio e nunca é alterado. O container só enxerga as pastas
montadas no mesmo caminho do Mac (raiz dos notebooks, warehouse e, se informada, Connections); nada
de `~/.aws` nem de `catalog.db`. Chamadas ao CLI usam argv fixo (ver `cli`) e o log do job nunca
contém o `$HOME` do operador.
"""

import asyncio
import json
import logging
import re
import shutil
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...config import default_root
from ...jobs import Job, JobRegistry
from ...spark.bundles import WAREHOUSE_DIR
from . import catalog, cli, kernelspec, launch

log = logging.getLogger(__name__)

PHASES = ("docker", "image", "container", "validate", "kernelspec")
OWNER_LABEL = "notisbook.owner"
OWNER_VALUE = "notisbook"
RUNTIME_LABEL = "notisbook.runtime"
VALIDATE_SCRIPT = "validate_runtime.py"
# Imagem Glue: ~5 GiB de conteúdo e ~12 GiB em disco; o disco do Colima é um arquivo no disco do Mac.
MIN_BUILD_FREE_BYTES = 15 * 1024**3
BUILD_TIMEOUT_S = 3600.0
VALIDATE_TIMEOUT_S = 900.0
INSPECT_TIMEOUT_S = 10.0
STOP_TIMEOUT_S = 60.0
_DOCKERFILE_PREVIEW_BYTES = 64 * 1024
_SENSITIVE_HOME_DIRS = (".aws", ".ssh", ".gnupg", ".kube", ".docker")
_FORBIDDEN_CHARS = re.compile(r"[,\"\x00-\x1f\x7f]")
_FROM = re.compile(r"^\s*FROM\s+(\S+)", re.IGNORECASE | re.MULTILINE)


class InstallError(Exception):
    """Falha esperada do job de instalação; a mensagem vai ao operador."""


class InstallInProgress(Exception):
    """Já há job ou operação em andamento para o runtime."""


class SessionsActive(Exception):
    """Há sessão de kernel usando o runtime."""


class DockerUnavailable(Exception):
    """O daemon Docker não responde."""


class ContainerMissing(Exception):
    """O container do runtime não existe."""


class ContainerForeign(Exception):
    """Existe um container com o nome do runtime que não pertence ao Notisbook."""


class MountRejected(ValueError):
    """Pasta recusada para montagem; `field` é o campo do corpo da requisição."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class MountPlan:
    notebooks: Path
    warehouse: Path
    connections: Path | None = None

    @property
    def paths(self) -> list[Path]:
        ordered = [self.notebooks, self.warehouse, *([self.connections] if self.connections else [])]
        return list(dict.fromkeys(ordered))


@dataclass(frozen=True)
class ContainerInfo:
    status: str
    running: bool
    labels: dict[str, str]
    mounts: tuple[str, ...]

    def owned_by(self, runtime: catalog.DockerRuntime) -> bool:
        return self.labels.get(OWNER_LABEL) == OWNER_VALUE and self.labels.get(RUNTIME_LABEL) == runtime.key


def _parts(path: Path) -> tuple[str, ...]:
    # O APFS do Mac ignora caixa por padrão; comparar sem caixa só recusa mais.
    return tuple(part.casefold() for part in path.parts)


def _within(child: Path, parent: Path) -> bool:
    """True se `child` é `parent` ou está dentro dele."""
    base = _parts(parent)
    return _parts(child)[: len(base)] == base


def check_mount(raw: str, field: str, data_home: Path) -> Path:
    """Caminho resolvido de uma pasta montável; levanta `MountRejected`. I/O bloqueante.

    O Colima só compartilha o `$HOME` e o container usa rede host: recusa o próprio `$HOME`, seus
    ancestrais, pastas fora dele, diretórios sensíveis do home, a pasta de dados do Notisbook (que
    guarda o `catalog.db`) e qualquer pasta que a contenha. Dentro da pasta de dados só valem
    `notebooks/` e `warehouse/`. Vírgula e aspas ficam fora porque o `--mount` é CSV.
    """
    if not isinstance(raw, str) or not raw.startswith("/"):
        raise MountRejected(field, "O caminho deve ser absoluto")
    if _FORBIDDEN_CHARS.search(raw):
        raise MountRejected(field, "O caminho não pode conter vírgula, aspas ou caracteres de controle")
    try:
        resolved = Path(raw).resolve(strict=True)
    except FileNotFoundError as exc:
        raise MountRejected(field, "Pasta não encontrada") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise MountRejected(field, "Caminho inválido") from exc
    if _FORBIDDEN_CHARS.search(str(resolved)):
        raise MountRejected(field, "O caminho não pode conter vírgula, aspas ou caracteres de controle")
    if not resolved.is_dir():
        raise MountRejected(field, "Não é uma pasta")
    home = Path.home().resolve()
    data = data_home.resolve()
    if _within(home, resolved):
        raise MountRejected(field, "Não pode ser a pasta pessoal nem um ancestral dela")
    if not _within(resolved, home):
        raise MountRejected(field, "Deve ficar dentro da pasta pessoal (o Docker só compartilha o $HOME)")
    if any(_within(resolved, home / name) for name in _SENSITIVE_HOME_DIRS):
        raise MountRejected(field, "Pasta sensível do usuário não pode ser montada no container")
    if _within(data, resolved):
        raise MountRejected(field, "Não pode ser a pasta de dados do Notisbook nem conter ela")
    allowed_inside = (default_root(data), data / WAREHOUSE_DIR)
    if _within(resolved, data) and not any(_within(resolved, base) for base in allowed_inside):
        raise MountRejected(field, "Dentro da pasta de dados do Notisbook só são aceitas notebooks e warehouse")
    return resolved


def _parse_container(raw: dict[str, Any]) -> ContainerInfo:
    state = raw.get("State") or {}
    labels = (raw.get("Config") or {}).get("Labels") or {}
    mounts = tuple(
        str(m.get("Source"))
        for m in raw.get("Mounts") or []
        if m.get("Type") == "bind" and m.get("Source") == m.get("Destination")
    )
    return ContainerInfo(
        status=str(state.get("Status") or "unknown"),
        running=bool(state.get("Running")),
        labels={str(k): str(v) for k, v in labels.items()},
        mounts=mounts,
    )


def inspect_container(runtime: catalog.DockerRuntime) -> ContainerInfo | None:
    """None se o container não existe; `DockerError` se o daemon falhar. Bloqueante."""
    result = cli.run(["container", "inspect", runtime.container], timeout=INSPECT_TIMEOUT_S)
    if result.returncode != 0:
        if "no such" in result.stderr.lower():
            return None
        raise cli.DockerError("docker container inspect: falha ao consultar o container")
    try:
        return _parse_container(json.loads(result.stdout)[0])
    except (ValueError, IndexError, TypeError, AttributeError) as exc:
        raise cli.DockerError("docker container inspect: resposta inválida") from exc


def image_size(runtime: catalog.DockerRuntime) -> int | None:
    """Tamanho da imagem em bytes, ou None se ausente. Bloqueante."""
    result = cli.run(["image", "inspect", "--format", "{{.Size}}", runtime.image], timeout=INSPECT_TIMEOUT_S)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _dockerfile_info(runtime: catalog.DockerRuntime) -> dict[str, Any]:
    path = runtime.dockerfile_path
    try:
        with path.open("rb") as handle:
            text = handle.read(_DOCKERFILE_PREVIEW_BYTES).decode("utf-8", errors="replace")
    except OSError:
        text = ""
    match = _FROM.search(text)
    base, _, digest = (match.group(1) if match else "").partition("@")
    return {
        "path": path.relative_to(catalog.RUNTIMES_DIR.parent).as_posix(),
        "text": text,
        "base_image": base or None,
        "base_digest": digest or None,
    }


def _versions(checks: dict[str, Any]) -> dict[str, str]:
    """Versões relatadas pelas checagens do `validate_runtime` (python, spark, java, ...)."""
    found: dict[str, str] = {}
    for name, result in checks.items():
        if isinstance(result, dict) and isinstance(result.get("version"), str):
            found[name] = result["version"]
    return found


class DockerRuntimes:
    def __init__(
        self,
        home: Path,
        jobs: JobRegistry,
        notebooks_root: Callable[[], Path],
        has_active_session: Callable[[str], bool] | None = None,
    ) -> None:
        self._home = home
        self._jobs = jobs
        self._notebooks_root = notebooks_root
        self._has_active_session = has_active_session or (lambda _name: False)
        # kernel name -> (job id, kind); stop/restart/remove não têm job (id vazio).
        self._active: dict[str, tuple[str, str]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def try_acquire(self, name: str, job_id: str, kind: str) -> bool:
        """Lock por runtime, compartilhado por instalação, recriação, stop, restart e remoção."""
        if name in self._active:
            return False
        self._active[name] = (job_id, kind)
        return True

    def release(self, name: str) -> None:
        self._active.pop(name, None)

    def is_mutating(self, name: str, kind: str | None = None) -> bool:
        """True enquanto o lock do kernel `name` está tomado (por operação de `kind`, se dado)."""
        held = self._active.get(name)
        return held is not None and (kind is None or held[1] == kind)

    def active_job(self, name: str) -> tuple[str, str] | None:
        held = self._active.get(name)
        return held if held is not None and held[0] else None

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # --- montagens ---

    def plan_mounts(self, connections_dir: str | None) -> MountPlan:
        """Valida as pastas a montar (levanta `MountRejected`). I/O bloqueante: use `to_thread`."""
        warehouse = self._home / WAREHOUSE_DIR
        warehouse.mkdir(parents=True, exist_ok=True)
        return MountPlan(
            notebooks=check_mount(str(self._notebooks_root()), "notebooks_root", self._home),
            warehouse=check_mount(str(warehouse), "warehouse", self._home),
            connections=check_mount(connections_dir, "connections_dir", self._home) if connections_dir else None,
        )

    @staticmethod
    def _mount_drift(registered: tuple[str, ...], plan: MountPlan, check_connections: bool) -> dict[str, list[str]]:
        """Montagens que faltam e as que sobram no container em relação às atuais."""
        expected = {str(p) for p in (plan.paths if check_connections else [plan.notebooks, plan.warehouse])}
        have = set(registered)
        return {
            "missing": sorted(expected - have),
            "extra": sorted(have - expected) if check_connections else [],
        }

    # --- estado ---

    async def describe(self, runtime: catalog.DockerRuntime, connections_dir: str | None = None) -> dict[str, Any]:
        """Estado do runtime para a UI; sem Docker, só o que o disco informa (nunca levanta por isso)."""
        available = await asyncio.to_thread(cli.is_available)
        registration = await asyncio.to_thread(kernelspec.read_registration, runtime)
        saved = await asyncio.to_thread(kernelspec.read_packages, runtime) or {}
        held = self.active_job(runtime.kernel_name)
        state: dict[str, Any] = {
            "key": runtime.key,
            "label": runtime.label,
            "kernel_name": runtime.kernel_name,
            "formats": list(runtime.formats),
            "image": runtime.image,
            "container_name": runtime.container,
            "dockerfile": await asyncio.to_thread(_dockerfile_info, runtime),
            "available": available,
            "installed": registration is not None,
            "busy": self.is_mutating(runtime.kernel_name),
            "job": {"id": held[0], "kind": held[1]} if held else None,
            "image_present": None,
            "image_size": None,
            "container": None,
            "mounts": None,
            "versions": saved.get("versions") or {},
        }
        if not available:
            return state
        try:
            size = await asyncio.to_thread(image_size, runtime)
        except cli.DockerError as exc:
            log.warning("falha ao inspecionar a imagem: %s", exc)
        else:
            state["image_present"] = size is not None
            state["image_size"] = size
        try:
            info = await asyncio.to_thread(inspect_container, runtime)
        except cli.DockerError as exc:
            log.warning("falha ao inspecionar o container: %s", exc)
            info = None
        state["container"] = (
            None
            if info is None
            else {"status": info.status, "running": info.running, "owned": info.owned_by(runtime)}
        )
        state["mounts"] = await self._mounts_state(info, connections_dir)
        return state

    async def _mounts_state(self, info: ContainerInfo | None, connections_dir: str | None) -> dict[str, Any]:
        registered = list(info.mounts) if info is not None else []
        body: dict[str, Any] = {"registered": registered, "current": None, "stale": False, "missing": [], "extra": [], "error": None}
        try:
            plan = await asyncio.to_thread(self.plan_mounts, connections_dir)
        except MountRejected as exc:
            body["error"] = f"{exc.field}: {exc.message}"
            return body
        except OSError:
            body["error"] = "não foi possível preparar a pasta warehouse"
            return body
        body["current"] = [str(p) for p in plan.paths]
        if info is not None:
            drift = self._mount_drift(info.mounts, plan, check_connections=connections_dir is not None)
            body.update(drift, stale=bool(drift["missing"] or drift["extra"]))
        return body

    async def details(self, runtime: catalog.DockerRuntime, connections_dir: str | None = None) -> dict[str, Any]:
        """`describe` mais python e pacotes gravados na instalação (somente leitura)."""
        state = await self.describe(runtime, connections_dir)
        saved = await asyncio.to_thread(kernelspec.read_packages, runtime) or {}
        state["python"] = saved.get("python")
        state["packages"] = saved.get("packages") or []
        return state

    # --- instalação ---

    def start_install(self, runtime: catalog.DockerRuntime, plan: MountPlan, recreate: bool) -> Job:
        """Registra o job e o executa em segundo plano.

        Síncrono de propósito: a checagem de sessões e o lock não têm `await` entre si.
        """
        name = runtime.kernel_name
        if recreate and self._has_active_session(name):
            raise SessionsActive(runtime.key)
        if self.is_mutating(name):
            raise InstallInProgress(runtime.key)
        job = self._jobs.create("docker-recreate" if recreate else "docker-install", runtime.key)
        self.try_acquire(name, job.id, "recreate" if recreate else "install")
        self._spawn(self._run(job, runtime, plan, recreate))
        return job

    async def _run(self, job: Job, runtime: catalog.DockerRuntime, plan: MountPlan, recreate: bool) -> None:
        try:
            await job.start()
            await self._phase_docker(job)
            await self._phase_image(job, runtime)
            await self._phase_container(job, runtime, plan, recreate)
            checks = await self._phase_validate(job, runtime)
            await self._phase_kernelspec(job, runtime, checks)
            await job.finish("succeeded")
        except asyncio.CancelledError:
            await job.finish("failed", "cancelado")
            raise
        except InstallError as exc:
            await job.finish("failed", cli.redact_home(str(exc)))
        except (cli.DockerError, launch.LaunchError, OSError) as exc:
            log.warning("instalação do runtime %s falhou: %s", runtime.key, type(exc).__name__)
            await job.finish("failed", cli.redact_home(str(exc)) or type(exc).__name__)
        except Exception:
            log.exception("falha inesperada instalando o runtime %s", runtime.key)
            await job.finish("failed", "erro inesperado; veja o log do servidor")
        finally:
            self.release(runtime.kernel_name)

    @staticmethod
    async def _emit(job: Job, phase: str, line: str) -> None:
        await job.emit(phase, cli.redact_home(line), PHASES.index(phase) / len(PHASES))

    async def _phase_docker(self, job: Job) -> None:
        await self._emit(job, "docker", "Verificando o Docker")
        result = await asyncio.to_thread(self._server_version)
        if result is None:
            raise InstallError("Docker indisponível: inicie o Colima (ou o daemon Docker) e tente de novo")
        await self._emit(job, "docker", f"Docker disponível (servidor {result})")

    @staticmethod
    def _server_version() -> str | None:
        try:
            out = cli.run(["info", "--format", "{{.ServerVersion}}"], timeout=cli.AVAILABILITY_TIMEOUT_S)
        except cli.DockerError:
            return None
        return out.stdout.strip() or "?" if out.returncode == 0 else None

    async def _phase_image(self, job: Job, runtime: catalog.DockerRuntime) -> None:
        await self._emit(job, "image", f"Verificando a imagem {runtime.image}")
        if await asyncio.to_thread(image_size, runtime) is not None:
            await self._emit(job, "image", f"Imagem {runtime.image} já existe; build pulado")
            return
        if not runtime.dockerfile_path.is_file():
            raise InstallError("Dockerfile do runtime não encontrado no pacote")
        free = await asyncio.to_thread(lambda: shutil.disk_usage(Path.home()).free)
        if free < MIN_BUILD_FREE_BYTES:
            raise InstallError(
                f"Espaço livre insuficiente para o build: {free / 1024**3:.1f} GiB livres, "
                f"são necessários cerca de {MIN_BUILD_FREE_BYTES // 1024**3} GiB"
            )
        await self._emit(job, "image", f"Imagem ausente; construindo {runtime.image} (pode levar vários minutos)")

        async def forward(line: str) -> None:
            await job.emit("image", line, PHASES.index("image") / len(PHASES))

        code = await cli.stream(
            ["build", "--progress=plain", "-t", runtime.image, "-f", str(runtime.dockerfile_path), str(runtime.context_dir)],
            forward,
            timeout=BUILD_TIMEOUT_S,
        )
        if code != 0:
            raise InstallError(f"O build da imagem falhou (código {code})")
        await self._emit(job, "image", f"Imagem {runtime.image} construída")

    async def _phase_container(
        self, job: Job, runtime: catalog.DockerRuntime, plan: MountPlan, recreate: bool
    ) -> None:
        name = runtime.container
        await self._emit(job, "container", f"Verificando o container {name}")
        info = await asyncio.to_thread(inspect_container, runtime)
        if info is not None and not info.owned_by(runtime):
            raise InstallError(
                f"Já existe um container chamado {name} que não pertence ao Notisbook; "
                "ele não foi alterado. Remova ou renomeie esse container e tente de novo"
            )
        if info is not None and recreate:
            await self._emit(job, "container", "Removendo o container anterior para recriá-lo")
            await self._docker_ok(["rm", "-f", name], "remover o container anterior")
            info = None
        if info is None:
            await self._emit(job, "container", "Criando o container com as pastas montadas:")
            for path in plan.paths:
                await self._emit(job, "container", f"  {path}")
            await self._docker_ok(self._run_args(runtime, plan), "criar o container", timeout=120.0)
            await self._emit(job, "container", f"Container {name} criado e iniciado")
            return
        drift = self._mount_drift(info.mounts, plan, check_connections=plan.connections is not None)
        if drift["missing"] or drift["extra"]:
            raise InstallError("As pastas montadas no container estão defasadas; use Recriar para aplicar as atuais")
        if not info.running:
            await self._docker_ok(["start", name], "iniciar o container", timeout=launch.START_TIMEOUT_S)
        await self._emit(job, "container", f"Container {name} já existe com as pastas atuais; reaproveitado")

    @staticmethod
    def _run_args(runtime: catalog.DockerRuntime, plan: MountPlan) -> list[str]:
        args = [
            "run", "-d",
            "--name", runtime.container,
            "--label", f"{OWNER_LABEL}={OWNER_VALUE}",
            "--label", f"{RUNTIME_LABEL}={runtime.key}",
            "--init",
            "--network", "host",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/run/notisbook:mode=1777",
            "--restart", "no",
            "--user", "hadoop",
        ]  # fmt: skip
        for path in plan.paths:
            args += ["--mount", f"type=bind,source={path},target={path}"]
        return [*args, runtime.image]

    @staticmethod
    async def _docker_ok(args: list[str], action: str, timeout: float = 60.0) -> None:
        result = await asyncio.to_thread(lambda: cli.run(args, timeout=timeout))
        if result.returncode != 0:
            tail = cli.redact_home((result.stderr.strip().splitlines() or [""])[-1])[:300]
            raise InstallError(f"Não foi possível {action}" + (f": {tail}" if tail else ""))

    async def _phase_validate(self, job: Job, runtime: catalog.DockerRuntime) -> dict[str, Any]:
        await self._emit(job, "validate", "Validando o runtime dentro do container (Spark, Glue e kernel)")
        script = (runtime.context_dir / VALIDATE_SCRIPT).read_text(encoding="utf-8")
        result = await asyncio.to_thread(
            lambda: cli.run(["exec", "-i", runtime.container, "python3", "-"], input_text=script, timeout=VALIDATE_TIMEOUT_S)
        )
        try:
            checks = json.loads(result.stdout)
        except ValueError:
            tail = cli.redact_home((result.stderr.strip().splitlines() or [""])[-1])[:300]
            raise InstallError("A validação não produziu resultado" + (f": {tail}" if tail else "")) from None
        if not isinstance(checks, dict):
            raise InstallError("A validação produziu um resultado inválido")
        failed: list[str] = []
        for check, outcome in checks.items():
            ok = isinstance(outcome, dict) and outcome.get("ok") is True
            detail = "" if ok else f" ({outcome.get('error', 'sem detalhe')})" if isinstance(outcome, dict) else ""
            await self._emit(job, "validate", f"{check}: {'ok' if ok else 'FALHOU'}{detail}")
            if not ok:
                failed.append(check)
        if failed or result.returncode != 0:
            raise InstallError("A validação do runtime falhou: " + (", ".join(failed) or f"código {result.returncode}"))
        return checks

    async def _phase_kernelspec(self, job: Job, runtime: catalog.DockerRuntime, checks: dict[str, Any]) -> None:
        await self._emit(job, "kernelspec", f"Gravando o kernelspec {runtime.kernel_name}")
        data = await asyncio.to_thread(launch.packages, runtime)
        data["versions"] = _versions(checks)
        await asyncio.to_thread(kernelspec.write_kernelspec, runtime, data)

    # --- stop / restart / remove ---

    async def _control(self, runtime: catalog.DockerRuntime, kind: str, action: Callable[[ContainerInfo | None], None]) -> None:
        """Roda `action` (bloqueante, em thread) sob o lock do runtime; exige Docker e container do app."""
        name = runtime.kernel_name
        if self._has_active_session(name):
            raise SessionsActive(runtime.key)
        if not self.try_acquire(name, "", kind):
            raise InstallInProgress(runtime.key)
        try:
            if not await asyncio.to_thread(cli.is_available):
                raise DockerUnavailable
            info = await asyncio.to_thread(inspect_container, runtime)
            if info is not None and not info.owned_by(runtime):
                raise ContainerForeign(runtime.container)
            await asyncio.to_thread(action, info)
        finally:
            self.release(name)

    async def stop(self, runtime: catalog.DockerRuntime) -> None:
        def act(info: ContainerInfo | None) -> None:
            if info is None:
                raise ContainerMissing(runtime.container)
            self._docker_must(["stop", "-t", "10", runtime.container], STOP_TIMEOUT_S, "parar")

        await self._control(runtime, "stop", act)

    async def restart(self, runtime: catalog.DockerRuntime) -> None:
        def act(info: ContainerInfo | None) -> None:
            if info is None:
                raise ContainerMissing(runtime.container)
            self._docker_must(["restart", "-t", "10", runtime.container], STOP_TIMEOUT_S, "reiniciar")

        await self._control(runtime, "restart", act)

    async def remove(self, runtime: catalog.DockerRuntime) -> None:
        """Apaga o container e o kernelspec; a imagem é mantida."""

        def act(info: ContainerInfo | None) -> None:
            registered = kernelspec.read_registration(runtime) is not None
            if info is None and not registered:
                raise ContainerMissing(runtime.container)
            if info is not None:
                self._docker_must(["rm", "-f", runtime.container], STOP_TIMEOUT_S, "remover")
            kernelspec.remove_kernelspec(runtime)

        await self._control(runtime, "remove", act)

    @staticmethod
    def _docker_must(args: list[str], timeout: float, verb: str) -> None:
        result = cli.run(args, timeout=timeout)
        if result.returncode != 0:
            raise cli.DockerError(f"docker: não foi possível {verb} o container")
