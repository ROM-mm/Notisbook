"""Catálogo para o runtime Docker: o kernel no container lê e grava o registro `nb_*` só por aqui.

O backend é o único escritor do `catalog.db` para o lado Docker. Autenticação por token de runtime da
sessão (nunca o token da UI) e regra de Host própria. O plano do hook é validado antes de tocar o banco:
formato, nomes, tamanho e `location`: local por realpath dentro das pastas montadas na sessão, ou `s3a` do
notislake em forma estrita. Não há warehouse local: MANAGED só existe em `s3a`, na forma `<camada>/<t>`. Corpo
malformado recusa o plano (422); item inválido por regra ou limite sai em `rejected` e os demais são gravados numa
só transação, onde `apply_plan` ainda aplica camada pelo schema, sobreposição e nome repetido no Iceberg. A exclusão de pastas MANAGED é decidida pela linha do registro, depois do COMMIT: as s3a o backend
devolve em `deletions` para o kernel apagar; ele nunca apaga arquivos (uma linha MANAGED legada com location
local volta em `files_kept`). Respostas e logs não carregam segredo.
"""

import asyncio
import json
import logging
import os
import sqlite3
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

from ..catalog import glue_repo, iceberg_jdbc, registry
from ..catalog.store import catalog_db_path, connect, ensure_catalog_db
from ..fs_safety import is_within
from ..notislake import locations as notislake_locations
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
Format = Literal["delta", "parquet", "hudi"]
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
    # Itens de tabela chegam crus e são validados um a um (`_parse_items`): limite estourado recusa só o item.
    created: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    updated: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    renamed: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    dropped: list[Dropped] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    # Sai só do registro (a tabela ainda existe no Spark): nunca apaga arquivos. Mesmo formato de `dropped`.
    unregistered: list[Dropped] = Field(default_factory=list, max_length=MAX_PLAN_ITEMS)
    new_dbs: list[Name] = Field(default_factory=list, max_length=MAX_DBS)
    gone_dbs: list[Name] = Field(default_factory=list, max_length=MAX_DBS)

    def item_count(self) -> int:
        return len(self.created) + len(self.updated) + len(self.renamed) + len(self.dropped) + len(self.unregistered)


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
    """Código do erro se a `location` não é local dentro das pastas montadas nem `s3a` válida do notislake.

    O ramo local só vê caminhos do usuário (montagens); uma URI `s3a` nunca chega ao `os.path`.
    """
    if location.startswith(f"{notislake_locations.SCHEME}://"):
        return _s3a_location_error(location)
    path = registry.local_path(location)
    if path is None:
        return "location_not_local"
    real = Path(os.path.realpath(path))
    for root in grant.roots:
        base = Path(os.path.realpath(root))
        if real != base and is_within(real, base):
            return None
    return "location_outside_mounts"


def _s3a_location_error(location: str) -> str | None:
    """Só a forma; camada, sobreposição e nome repetido são decididos no `apply_plan` (`rejected` com o código)."""
    try:
        notislake_locations.parse_notislake(location)
    except notislake_locations.InvalidLocation:
        return "location_not_notislake"
    return None


LIMIT_ERRORS = frozenset({"string_too_long", "too_long", "string_pattern_mismatch"})
MAX_KEY_PART = 128


def _raw_key(section: str, raw: dict[str, Any]) -> tuple[str, str] | None:
    """(db, name) do item cru para devolvê-lo em `rejected`; `None` se não der para identificá-lo."""
    db, name = (raw.get("new_db"), raw.get("new_name")) if section == "renamed" else (raw.get("db"), raw.get("name"))
    if isinstance(db, str) and isinstance(name, str) and len(db) <= MAX_KEY_PART and len(name) <= MAX_KEY_PART:
        return db, name
    return None


def _parse_items[M: BaseModel](
    section: str, raw_items: list[dict[str, Any]], model: type[M], rejected: list[dict[str, Any]]
) -> list[M]:
    """Valida item a item. Estouro de tamanho/formato recusa só o item; qualquer outro erro é corpo malformado (422)."""
    valid: list[M] = []
    for index, raw in enumerate(raw_items):
        try:
            valid.append(model.model_validate(raw))
        except ValidationError as exc:
            errors = exc.errors()
            key = _raw_key(section, raw)
            if key is None or any(e["type"] not in LIMIT_ERRORS for e in errors):
                detail = [{"loc": [section, str(index), *(str(p) for p in e["loc"])], "msg": e["msg"]} for e in errors[:10]]
                raise HTTPException(422, detail) from None
            rejected.append({"key": list(key), "reason": "item_limits"})
    return valid


def _created_error(item: Created, grant: RuntimeGrant) -> str | None:
    error = _location_error(item.loc, grant)
    if error or item.type != "MANAGED":
        return error
    return None if notislake_locations.managed_table(item.loc) else "managed_location_rejected"


def _glue_refusal(body: PlanBody) -> list[dict[str, Any]]:
    """Todo item de tabela do plano como `glue_runtime`; só os identificáveis voltam (`key`), sem eco de valores."""
    keys = [
        key
        for section, items in (("created", body.created), ("updated", body.updated), ("renamed", body.renamed))
        for key in (_raw_key(section, raw) for raw in items)
        if key is not None
    ]
    keys += [(d.db, d.name) for d in (*body.dropped, *body.unregistered)]
    return [{"key": list(key), "reason": "glue_runtime"} for key in keys]


def _build_plan(body: PlanBody, grant: RuntimeGrant) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Plano do `apply_plan` só com os itens válidos e a lista dos recusados (`key`, `reason`); sem eco de valores.

    O runtime Glue nunca grava em `nb_*`: o plano volta vazio e todo item de tabela em `rejected` (`glue_runtime`).
    """
    if grant.glue:
        empty: dict[str, Any] = {key: [] for key in ("created", "updated", "renamed", "dropped", "unregistered", "new_dbs", "gone_dbs")}
        return empty, _glue_refusal(body)
    rejected: list[dict[str, Any]] = []
    created, updated, renamed = [], [], []
    for item in _parse_items("created", body.created, Created, rejected):
        error = _created_error(item, grant)
        if error:
            rejected.append({"key": [item.db, item.name], "reason": error})
            continue
        created.append(((item.db, item.name), {**_info(item), "type": item.type, "description": item.description}))
    for u in _parse_items("updated", body.updated, Updated, rejected):
        error = _location_error(u.loc, grant)
        if error:
            rejected.append({"key": [u.db, u.name], "reason": error})
            continue
        updated.append(((u.db, u.name), u.expected_loc, "EXTERNAL", _info(u)))
    for r in _parse_items("renamed", body.renamed, Renamed, rejected):
        error = _location_error(r.loc, grant)
        if error:
            rejected.append({"key": [r.new_db, r.new_name], "reason": error})
            continue
        renamed.append(((r.old_db, r.old_name), (r.new_db, r.new_name), r.expected_loc, _info(r)))
    plan = {
        "created": created,
        "updated": updated,
        "renamed": renamed,
        "dropped": [((d.db, d.name), d.expected_loc) for d in body.dropped],
        "unregistered": [((d.db, d.name), d.expected_loc) for d in body.unregistered],
        "new_dbs": sorted(set(body.new_dbs)),
        "gone_dbs": sorted(set(body.gone_dbs)),
    }
    return plan, rejected


def _managed_shape(location: str) -> bool:
    """Só `s3a://notislake/<camada>/<t>` é MANAGED; nenhum caminho local o é."""
    return notislake_locations.managed_table(location)


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


def _iceberg_tables(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Tabelas do catálogo `iceberg` (`db`, `name`, `loc`) para o hook checar nome repetido e sobreposição antes de gravar.

    `loc` é a pasta `s3a://notislake/...` da tabela (pai de `metadata/`), ou `None` se o metadata não está no
    notislake. Catálogo Iceberg ausente ou em formato desconhecido dá lista vazia.
    """
    try:
        iceberg_jdbc.check_schema(conn)
        rows = conn.execute(
            "SELECT table_namespace, table_name, metadata_location FROM iceberg_tables WHERE catalog_name = ? "
            "ORDER BY table_namespace, table_name",
            (iceberg_jdbc.ICEBERG_CATALOG,),
        ).fetchall()
    except (iceberg_jdbc.UnsupportedIcebergSchema, sqlite3.OperationalError):
        return []
    return [{"db": r[0], "name": r[1], "loc": iceberg_jdbc.table_prefix(r[2])} for r in rows]


def _registry(home: Path) -> dict[str, Any]:
    conn = _open_read(home)
    if conn is None:
        return {"generation": 0, "tables": [], "namespaces": [], "iceberg": [], "glue": []}
    try:
        generation, rows, namespaces = registry.read_snapshot(conn)
        iceberg = _iceberg_tables(conn)
        glue = glue_repo.registry_tables(conn)
    finally:
        conn.close()
    tables = [{"db": db, "name": name, **row} for (db, name), row in sorted(rows.items())]
    return {"generation": generation, "tables": tables, "namespaces": sorted(namespaces), "iceberg": iceberg, "glue": glue}


def _apply_or_skip(home: Path, plan: dict[str, Any], grant: RuntimeGrant) -> dict[str, Any]:
    """`_apply`, exceto para o runtime Glue: nada é gravado (o banco só é lido, para a `generation`)."""
    if not grant.glue:
        return _apply(home, plan)
    generation = _generation(home)
    return {
        "changed": False, "adopted": [], "conflicts": [], "rejected": [], "updated_ok": [], "renamed_ok": [],
        "dropped_ok": [], "files_kept": [], "deletions": [], "generation_before": generation, "generation": generation,
    }


def _apply(home: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Transação do plano; depois do COMMIT devolve as exclusões MANAGED que a própria linha autoriza.

    As s3a voltam em `deletions` (`key`, `loc`): quem apaga é o kernel. Uma location local MANAGED (legada) é
    mantida e vai em `files_kept`: o backend não apaga arquivos.
    """
    if not catalog_db_path(home).exists():
        ensure_catalog_db(home)
    conn = connect(home)
    try:
        result = registry.commit_plan(conn, plan, _managed_shape)
    finally:
        conn.close()
    kept = list(result["files_kept"])
    s3a_deletions = []
    for key, location in result["deletions"]:
        if location.startswith(f"{notislake_locations.SCHEME}://"):
            s3a_deletions.append({"key": key, "loc": location})
            continue
        kept.append(key)
    return {
        "changed": result["changed"],
        "adopted": result["adopted"],
        "conflicts": result["conflicts"],
        "rejected": [{"key": list(key), "reason": reason} for key, reason in result["rejected"]],
        "updated_ok": [{"key": key, "type": change["type"]} for key, change in result["updated_ok"]],
        "renamed_ok": [{"old": old, "new": new} for old, new, _ in result["renamed_ok"]],
        "dropped_ok": result["dropped_ok"],
        "files_kept": kept,
        "deletions": s3a_deletions,
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
    """Aplica o plano do hook. 413 corpo grande, 422 corpo malformado (nada é gravado), 503 db ocupado.

    Item inválido por regra ou limite não derruba o plano: volta em `rejected` (`key`, `reason`).
    """
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
    plan, rejected = _build_plan(body, grant)
    try:
        result = await asyncio.to_thread(_apply_or_skip, _home(request), plan, grant)
    except sqlite3.Error as exc:
        raise _sqlite_http(exc) from exc
    log.info(
        "runtime catalog plan: created=%d updated=%d renamed=%d dropped=%d unregistered=%d rejected=%d",
        len(plan["created"]), len(plan["updated"]), len(plan["renamed"]), len(plan["dropped"]),
        len(plan["unregistered"]), len(rejected),
    )
    return {**result, "rejected": [*rejected, *result["rejected"]]}
