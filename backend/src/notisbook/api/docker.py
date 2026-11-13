"""Runtimes Docker: estado, instalação/recriação por job, stop, restart, detalhes e remoção."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..runtimes.docker import catalog, cli
from ..runtimes.docker.service import (
    ContainerForeign,
    ContainerMissing,
    DockerRuntimes,
    DockerUnavailable,
    InstallInProgress,
    MountPlan,
    MountRejected,
    SessionsActive,
)
from ..security import require_token, require_trusted_host

MAX_PATH_LENGTH = 4096

# Token primeiro (401), depois Host (403).
router = APIRouter(prefix="/api/docker", dependencies=[Depends(require_token), Depends(require_trusted_host)])


def get_service(request: Request) -> DockerRuntimes:
    return request.app.state.docker


Service = Annotated[DockerRuntimes, Depends(get_service)]
ConnectionsDir = Annotated[str | None, Query(max_length=MAX_PATH_LENGTH)]


class InstallBody(BaseModel):
    """`connections_dir` é a pasta Connections do cliente (o backend não a conhece); `recreate` apaga o container atual."""

    connections_dir: str | None = None
    recreate: bool = False


def _runtime(key: str) -> catalog.DockerRuntime:
    runtime = catalog.get(key)
    if runtime is None:
        raise HTTPException(404, f"Runtime Docker desconhecido: {key}")
    return runtime


def _rejected(exc: MountRejected) -> HTTPException:
    return HTTPException(422, detail=[{"loc": ["body", exc.field], "msg": exc.message}])


async def _guarded(call: Any, runtime: catalog.DockerRuntime) -> None:
    """Executa stop/restart/remove traduzindo as falhas esperadas em status HTTP."""
    try:
        await call(runtime)
    except SessionsActive as exc:
        raise HTTPException(409, "O runtime tem sessões de kernel ativas; feche-as antes") from exc
    except InstallInProgress as exc:
        raise HTTPException(409, "Há outra operação em andamento neste runtime") from exc
    except DockerUnavailable as exc:
        raise HTTPException(503, "Docker indisponível: inicie o Colima (ou o daemon Docker)") from exc
    except ContainerForeign as exc:
        raise HTTPException(409, "O container com esse nome não pertence ao Notisbook; ele não foi alterado") from exc
    except ContainerMissing as exc:
        raise HTTPException(404, "O container do runtime não existe") from exc
    except cli.DockerError as exc:
        raise HTTPException(500, cli.redact_home(str(exc))) from exc
    except OSError as exc:
        raise HTTPException(500, "Não foi possível apagar o kernelspec do runtime") from exc


@router.get("/runtimes")
async def list_runtimes(service: Service, connections_dir: ConnectionsDir = None) -> dict[str, Any]:
    states = [await service.describe(runtime, connections_dir) for runtime in catalog.CATALOG]
    return {"available": all(state["available"] for state in states), "runtimes": states}


@router.post("/runtimes/{key}/install", status_code=202)
async def install_runtime(key: str, service: Service, body: InstallBody | None = None) -> dict[str, str]:
    runtime = _runtime(key)
    options = body or InstallBody()
    try:
        plan: MountPlan = await asyncio.to_thread(service.plan_mounts, options.connections_dir)
    except MountRejected as exc:
        raise _rejected(exc) from exc
    except OSError as exc:
        raise HTTPException(500, "Não foi possível preparar a pasta warehouse") from exc
    try:
        job = service.start_install(runtime, plan, options.recreate)
    except SessionsActive as exc:
        raise HTTPException(409, "O runtime tem sessões de kernel ativas; feche-as antes de recriar") from exc
    except InstallInProgress as exc:
        raise HTTPException(409, "Há outra operação em andamento neste runtime") from exc
    return {"job_id": job.id}


@router.post("/runtimes/{key}/stop", status_code=204)
async def stop_runtime(key: str, service: Service) -> None:
    await _guarded(service.stop, _runtime(key))


@router.post("/runtimes/{key}/restart", status_code=204)
async def restart_runtime(key: str, service: Service) -> None:
    await _guarded(service.restart, _runtime(key))


@router.get("/runtimes/{key}/details")
async def runtime_details(key: str, service: Service, connections_dir: ConnectionsDir = None) -> dict[str, Any]:
    return await service.details(_runtime(key), connections_dir)


@router.delete("/runtimes/{key}", status_code=204)
async def remove_runtime(key: str, service: Service) -> None:
    await _guarded(service.remove, _runtime(key))
