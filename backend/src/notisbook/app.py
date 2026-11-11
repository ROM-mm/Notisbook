"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from .api import catalog, contents, export, files, jobs, notebooks_root, sessions, spark, system, variables
from .config import Settings
from .jobs import JobRegistry
from .kernels.service import KernelService
from .notebooks.store import NotebookStore
from .preferences import protected_paths
from .spark.catalog import CatalogService
from .spark.installer import SparkInstaller
from .static import mount_frontend


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    kernels: KernelService = app.state.kernels
    kernels.cleanup_orphans()
    installer: SparkInstaller = app.state.installer
    await asyncio.to_thread(installer.sweep_trash)
    try:
        yield
    finally:
        await installer.shutdown()
        await kernels.shutdown_all()


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Notisbook", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.store = NotebookStore(settings.root, protected_paths(settings.home))
    app.state.root_source = settings.root_source
    app.state.root_generation = 0
    app.state.kernels = KernelService(settings.port, home=settings.home)
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
    app.include_router(system.router)
    app.include_router(contents.router)
    app.include_router(export.router)
    app.include_router(files.router)
    app.include_router(notebooks_root.router)
    app.include_router(sessions.router)
    app.include_router(catalog.router)
    app.include_router(variables.router)
    app.include_router(sessions.ws_router)
    app.include_router(spark.router)
    app.include_router(jobs.router)
    app.include_router(jobs.ws_router)
    mount_frontend(app, settings.frontend_dist)

    @app.middleware("http")
    async def identify(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Unauthenticated marker so start.sh can tell a running Notisbook from another process.
        response = await call_next(request)
        response.headers["X-Notisbook"] = "1"
        return response

    return app
