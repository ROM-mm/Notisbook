"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from .api import catalog, contents, docker, export, files, iceberg_rest, jobs, lifecycle, notebooks_root, notislake as notislake_api, runtime_catalog, sessions, spark, system
from .config import Settings
from .jobs import JobRegistry
from .kernels.service import KernelService
from .notebooks.store import NotebookStore
from .notislake.supervisor import NotislakeSupervisor
from .preferences import protected_paths
from .runtimes.docker.service import DockerRuntimes
from .spark.catalog import CatalogService
from .spark.installer import SparkInstaller
from .static import mount_frontend


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    kernels: KernelService = app.state.kernels
    kernels.cleanup_orphans()
    kernels.start_docker_sweep()
    installer: SparkInstaller = app.state.installer
    docker: DockerRuntimes = app.state.docker
    await asyncio.to_thread(installer.sweep_trash)
    try:
        yield
    finally:
        await installer.shutdown()
        await docker.shutdown()
        await kernels.shutdown_all()
        await kernels.stop_docker_runtimes()


def create_app(
    settings: Settings,
    notislake: NotislakeSupervisor | None = None,
    control: lifecycle.LifecycleControl | None = None,
) -> FastAPI:
    app = FastAPI(title="Notisbook", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.store = NotebookStore(settings.root, protected_paths(settings.home))
    app.state.root_source = settings.root_source
    app.state.root_generation = 0
    app.state.kernels = KernelService(settings.port, home=settings.home)
    app.state.notislake = notislake
    app.state.lifecycle = control
    app.state.channels = {}
    app.state.jobs = JobRegistry()
    kernels = app.state.kernels
    app.state.installer = SparkInstaller(
        settings.home,
        app.state.jobs,
        kernels.has_session,
        settings.pypi_url,
    )
    app.state.catalog = CatalogService(settings.pypi_url)
    app.state.docker = DockerRuntimes(
        settings.home,
        app.state.jobs,
        lambda: app.state.store.root,
        kernels.has_session,
    )
    kernels.bind_docker(app.state.docker)
    kernels.bind_notislake(notislake)
    app.include_router(system.router)
    app.include_router(contents.router)
    app.include_router(export.router)
    app.include_router(files.router)
    app.include_router(notebooks_root.router)
    app.include_router(sessions.router)
    app.include_router(catalog.router)
    app.include_router(runtime_catalog.router)
    app.include_router(iceberg_rest.router)
    app.add_exception_handler(iceberg_rest.IcebergError, iceberg_rest.handle_error)
    app.include_router(sessions.ws_router)
    app.include_router(spark.router)
    app.include_router(docker.router)
    app.include_router(jobs.router)
    app.include_router(jobs.ws_router)
    app.include_router(notislake_api.router)
    app.include_router(lifecycle.router)
    mount_frontend(app, settings.frontend_dist)

    @app.middleware("http")
    async def identify(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Unauthenticated marker so start.sh can tell a running Notisbook from another process.
        response = await call_next(request)
        response.headers["X-Notisbook"] = "1"
        return response

    return app
