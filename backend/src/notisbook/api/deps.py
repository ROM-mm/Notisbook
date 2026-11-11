"""Dependências FastAPI compartilhadas entre os routers."""

from typing import Annotated

from fastapi import Depends, Request

from ..kernels.service import KernelService


def get_kernels(request: Request) -> KernelService:
    return request.app.state.kernels


Kernels = Annotated[KernelService, Depends(get_kernels)]
