"""Aparência: fontes instaladas no sistema (somente leitura)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from ..fonts import system_fonts
from ..security import require_token, require_trusted_host

router = APIRouter(
    prefix="/api/appearance",
    dependencies=[Depends(require_token), Depends(require_trusted_host)],
)


@router.get("/system-fonts")
async def get_system_fonts(refresh: Annotated[bool, Query()] = False) -> system_fonts.SystemFonts:
    return await run_in_threadpool(system_fonts.list_system_fonts, refresh)
