"""Catálogo para o runtime Docker: o kernel no container lê e grava o registro `nb_*` só por aqui.

O backend é o único escritor do `catalog.db` para o lado Docker. Autenticação por token de runtime da
sessão (nunca o token da UI) e regra de Host própria. O plano do hook é validado antes de tocar o banco:
formato, nomes, tamanho e `location` por realpath dentro das pastas montadas na sessão. A exclusão de
pastas MANAGED é decidida pela linha do registro, depois do COMMIT; respostas e logs não carregam segredo.
"""

import asyncio
import json
import logging
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationError,
)

from ..catalog import registry
from ..catalog.managed import delete_managed_table, managed_table_dir
from ..catalog.store import catalog_db_path, connect, ensure_catalog_db
from ..fs_safety import is_within
from ..security import RuntimeGrant, require_runtime_host, require_runtime_token

log = logging.getLogger(__name__)

# Token primeiro (401), depois Host (403), como no router do catálogo.
router = APIRouter(
    prefix="/api/runtime-catalog",
    dependencies=[Depends(require_runtime_token), Depends(require_runtime_host)],
)

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_PLAN_ITEMS = 1000
MAX_DBS = 200
MAX_COLUMNS = 2000
NAME_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_$-]*$"

Name = Annotated[str, StringConstraints(pattern=NAME_PATTERN, min_length=1, max_length=128)]
Location = Annotated[str, StringConstraints(min_length=1, max_length=4096, pattern=r"^[^\x00]*$")]
Text = Annotated[str, StringConstraints(max_length=20000)]
Format = Literal["delta", "parquet"]
Grant = Annotated[RuntimeGrant, Depends(require_runtime_token)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Column(_Model):
    name: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    data_type: Text
    nullable: StrictBool = True
    is_partition: StrictBool = False
    description: Annotated[str, StringConstraints(max_length=4096)] | None = None


class TableInfo(_Model):
    fmt: Format
    loc: Location
    cols: list[Column] = Field(max_length=MAX_COLUMNS)
    parts: list[Annotated[str, StringConstraints(max_length=256)]] = Field(max_length=MAX_COLUMNS)
    dv: StrictInt | None = Field(default=None, ge=0)
    hi: Annotated[str, StringConstraints(max_length=64)] | None = None


class Created(TableInfo):
    db: Name
    name: Name
    type: Literal["MANAGED", "EXTERNAL"]
    description: Annotated[str, StringConstraints(max_length=4096)] | None = None


class Updated(TableInfo):
    db: Name
    name: Name
    expected_loc: Location


class Renamed(TableInfo):
    old_db: Name
    old_name: Name
    new_db: Name
    new_name: Name
    expected_loc: Location


class Dropped(_Model):
    db: Name
    name: Name
    expected_loc: Location


class PlanBody(_Model):
    created: list[Created] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    updated: list[Updated] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    renamed: list[Renamed] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    dropped: list[Dropped] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    new_dbs: list[Name] = Field(default_factory=list, max_length=MAX_DBS)
    gone_dbs: list[Name] = Field(default_factory=list, max_length=MAX_DBS)

    def item_count(self) -> int:
        return len(self.created) + len(self.updated) + len(self.renamed) + len(self.dropped)


def _info(item: TableInfo) -> dict[str, Any]:
    return {
        "fmt": item.fmt,
        "loc": item.loc,
        "cols": [c.model_dump() for c in item.cols],
        "parts": list(item.parts),
        "dv": item.dv,
        "hi": item.hi,
    }


def _location_error(location: str, grant: RuntimeGrant) -> str | None:
    """Código do erro se a `location` não é uma pasta local estritamente dentro das pastas montadas da sessão."""
    path = registry.local_path(location)
    if path is None:
        return "location_not_local"
    real = Path(os.path.realpath(path))
    iceberg = Path(os.path.realpath(grant.iceberg_root))
    if is_within(real, iceberg, fold=True):  # APFS ignora a caixa: `ICEBERG` é o mesmo warehouse
        return "location_in_iceberg_warehouse"
    for root in grant.roots:
        base = Path(os.path.realpath(root))
        if real != base and is_within(real, base):
            return None
    return "location_outside_mounts"


def _build_plan(body: PlanBody, grant: RuntimeGrant) -> dict[str, Any]:
    """Converte o corpo no plano do `apply_plan`, recusando (422) o que sai das regras; sem eco de valores."""

    def check(location: str) -> None:
        error = _location_error(location, grant)
        if error:
            raise HTTPException(422, error)

    created = []
    for item in body.created:
        check(item.loc)
        if item.type == "MANAGED":
            path = registry.local_path(item.loc)
            if path is None or managed_table_dir(str(path), grant.managed_root)[1] is not None:
                raise HTTPException(422, "managed_location_rejected")
        created.append(((item.db, item.name), {**_info(item), "type": item.type, "description": item.description}))
    updated = []
    for u in body.updated:
        check(u.loc)
        updated.append(((u.db, u.name), u.expected_loc, "EXTERNAL", _info(u)))
    renamed = []
    for r in body.renamed:
        check(r.loc)
        renamed.append(((r.old_db, r.old_name), (r.new_db, r.new_name), r.expected_loc, _info(r)))
    return {
        "created": created,
        "updated": updated,
        "renamed": renamed,
        "dropped": [((d.db, d.name), d.expected_loc) for d in body.dropped],
        "new_dbs": sorted(set(body.new_dbs)),
        "gone_dbs": sorted(set(body.gone_dbs)),
    }


def _managed_shape(grant: RuntimeGrant) -> Callable[[str], bool]:
    def shape(location: str) -> bool:
        path = registry.local_path(location)
        return path is not None and managed_table_dir(str(path), grant.managed_root)[1] is None

    return shape


async def _read_body(request: Request) -> bytes:
    """Corpo com teto de bytes, medido também sem Content-Length (chunked)."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        raise HTTPException(413, "body_too_large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(413, "body_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _sqlite_http(exc: sqlite3.Error) -> HTTPException:
    text = str(exc).lower()
    return HTTPException(503, "catalog_busy" if "locked" in text or "busy" in text else "catalog_unavailable")


def _home(request: Request) -> Path:
    home: Path = request.app.state.settings.home
    return home


def _open_read(home: Path) -> sqlite3.Connection | None:
    if not catalog_db_path(home).exists():
        return None
    conn = connect(home)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _generation(home: Path) -> int:
    conn = _open_read(home)
    if conn is None:
        return 0
    try:
        return registry.read_generation(conn)
    finally:
        conn.close()


def _registry(home: Path) -> dict[str, Any]:
    conn = _open_read(home)
    if conn is None:
        return {"generation": 0, "tables": [], "namespaces": []}
    try:
        generation, rows, namespaces = registry.read_snapshot(conn)
    finally:
        conn.close()
    tables = [{"db": db, "name": name, **row} for (db, name), row in sorted(rows.items())]
    return {"generation": generation, "tables": tables, "namespaces": sorted(namespaces)}


def _apply(home: Path, grant: RuntimeGrant, plan: dict[str, Any]) -> dict[str, Any]:
    """Transação do plano e, depois do COMMIT, a exclusão das pastas MANAGED que a própria linha autoriza."""
    if not catalog_db_path(home).exists():
        ensure_catalog_db(home)
    conn = connect(home)
    try:
        result = registry.commit_plan(conn, plan, _managed_shape(grant))
    finally:
        conn.close()
    kept = []
    for key, location in result["deletions"]:
        path = registry.local_path(location)
        if path is None or delete_managed_table(str(path), grant.managed_root):
            kept.append(key)
    return {
        "changed": result["changed"],
        "adopted": result["adopted"],
        "conflicts": result["conflicts"],
        "updated_ok": [{"key": key, "type": change["type"]} for key, change in result["updated_ok"]],
        "renamed_ok": [{"old": old, "new": new} for old, new, _ in result["renamed_ok"]],
        "dropped_ok": result["dropped_ok"],
        "files_kept": kept,
        "generation_before": result["generation_before"],
        "generation": result["generation"],
    }


@router.get("/generation")
async def get_generation(request: Request) -> dict[str, int]:
    try:
        return {"generation": await asyncio.to_thread(_generation, _home(request))}
    except sqlite3.Error as exc:
        raise _sqlite_http(exc) from exc


@router.get("/registry")
async def get_registry(request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_registry, _home(request))
    except sqlite3.Error as exc:
        raise _sqlite_http(exc) from exc


@router.post("/plan")
async def post_plan(request: Request, grant: Grant) -> dict[str, Any]:
    """Aplica o plano do hook. 413 corpo grande, 422 plano recusado (nada é gravado), 503 db ocupado."""
    raw = await _read_body(request)
    try:
        body = PlanBody.model_validate(json.loads(raw))
    except (ValueError, RecursionError) as exc:  # JSON inválido; `ValidationError` também é ValueError
        if isinstance(exc, ValidationError):
            detail = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()[:10]]
            raise HTTPException(422, detail) from None
        raise HTTPException(422, "invalid_json") from None
    if body.item_count() > MAX_PLAN_ITEMS:
        raise HTTPException(422, "plan_too_large")
    plan = _build_plan(body, grant)
    try:
        result = await asyncio.to_thread(_apply, _home(request), grant, plan)
    except sqlite3.Error as exc:
        raise _sqlite_http(exc) from exc
    log.info(
        "runtime catalog plan: created=%d updated=%d renamed=%d dropped=%d",
        len(body.created), len(body.updated), len(body.renamed), len(body.dropped),
    )
    return result
