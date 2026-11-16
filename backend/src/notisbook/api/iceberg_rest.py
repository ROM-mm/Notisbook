"""Iceberg REST catalog para o kernel Docker: o `SparkCatalog` do container usa o catálogo `iceberg` só por aqui.

Autenticação pelo token de runtime da sessão (o mesmo de `/api/runtime-catalog`, nunca o da UI) e regra de
Host de runtime. Todo erro sai como `ErrorModel` (`{"error": {message, type, code}}`), inclusive 401/403 de
autenticação. Recusa de operação é 403/400 (409 faria o cliente repetir; 5xx viraria estado de commit
desconhecido); 409 só para requisito violado ou CAS perdido, 500 só se o estado é realmente desconhecido.

No protocolo REST quem grava o `metadata.json` é o servidor: o `pyiceberg` (sem extras) entra só como biblioteca
de domínio (modelos, `validate`, `update_table_metadata`, serialização). A gravação do arquivo (criação exclusiva)
e o CAS de `metadata_location` usam o SQLite do backend, com o mesmo predicado do JdbcCatalog do runtime local.

Não há warehouse local. O namespace decide a camada: a location de uma tabela é `s3a://notislake/<camada>/<t>` (padrão
quando o cliente não envia `location`) ou, como externa, uma pasta da mesma camada ou uma pasta local montada na sessão.
Antes de gravar qualquer metadado o servidor recusa (400, com o código entre parênteses) namespace fora das camadas,
location fora da camada, pasta que se sobrepõe a outra tabela e nome `<ns>.<t>` já registrado no outro catálogo. O
backend nunca apaga arquivos de tabela: o purge de `s3a` é recusado e o de tabela local só remove a linha. Tabelas `s3a`
têm o metadata gravado por criação exclusiva no bucket, só com a conexão com que o kernel abriu (fingerprint).
"""

import asyncio
import hmac
import json
import logging
import os
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from pyiceberg.exceptions import CommitFailedException
from pyiceberg.partitioning import UNPARTITIONED_PARTITION_SPEC, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table.metadata import (
    TableMetadata,
    TableMetadataUtil,
    TableMetadataV1,
    TableMetadataV3,
    new_table_metadata,
)
from pyiceberg.table.sorting import UNSORTED_SORT_ORDER, SortOrder
from pyiceberg.table.update import (
    AssertCreate,
    SetLocationUpdate,
    TableRequirement,
    TableUpdate,
    UpgradeFormatVersionUpdate,
    update_table_metadata,
)

from ..catalog import iceberg_jdbc
from ..catalog.registry import ERR_NAME_IN_OTHER_CATALOG, all_table_locations, local_path, table_name_exists
from ..catalog.store import catalog_db_path, connect
from ..fs_safety import is_within
from ..notislake import locations, objectstore
from ..notislake.settings_store import ConfigInvalid
from ..notislake.sparkconf import fingerprint
from ..security import RuntimeGrant, require_runtime_host, require_runtime_token

log = logging.getLogger(__name__)

NAMESPACE_SEPARATOR = "\x1f"
MAX_NAME_LENGTH = 255
HADOOP_FILE_IO = "org.apache.iceberg.hadoop.HadoopFileIO"

ENDPOINTS = (
    "GET /v1/{prefix}/namespaces",
    "GET /v1/{prefix}/namespaces/{namespace}",
    "HEAD /v1/{prefix}/namespaces/{namespace}",
    "POST /v1/{prefix}/namespaces",
    "POST /v1/{prefix}/namespaces/{namespace}/properties",
    "DELETE /v1/{prefix}/namespaces/{namespace}",
    "GET /v1/{prefix}/namespaces/{namespace}/tables",
    "GET /v1/{prefix}/namespaces/{namespace}/tables/{table}",
    "HEAD /v1/{prefix}/namespaces/{namespace}/tables/{table}",
    "POST /v1/{prefix}/namespaces/{namespace}/tables",
    "POST /v1/{prefix}/namespaces/{namespace}/tables/{table}",
    "DELETE /v1/{prefix}/namespaces/{namespace}/tables/{table}",
    "POST /v1/{prefix}/tables/rename",
    "POST /v1/{prefix}/namespaces/{namespace}/tables/{table}/metrics",
)
CANNOT_DROP_LAYER = "cannot_drop_layer"
NOT_SUPPORTED_MESSAGE = "Operação não suportada pelo catálogo Iceberg do runtime Docker do Notisbook"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_UPDATES = 1000
MAX_PROPERTIES = 200
# Nomes novos viram pastas: mesmo padrão do catálogo de runtime.
# Os dois últimos são nomes legados que os location providers ainda honram quando `write.data.path` falta.
DATA_PATH_PROPERTIES = (
    "write.data.path",
    "write.metadata.path",
    "write.folder-storage.path",
    "write.object-storage.path",
)
LOCATION_PROVIDER_PROPERTY = "write.location-provider.impl"
NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_$-]{0,127}")
# Só o que o Spark 1.7 envia em CREATE/CTAS/INSERT/ALTER comuns; o resto (statistics, chaves de criptografia) é 400.
ALLOWED_ACTIONS = frozenset(
    {
        "assign-uuid",
        "upgrade-format-version",
        "add-schema",
        "set-current-schema",
        "add-spec",
        "set-default-spec",
        "add-sort-order",
        "set-default-sort-order",
        "set-location",
        "set-properties",
        "remove-properties",
        "add-snapshot",
        "set-snapshot-ref",
        "remove-snapshots",
        "remove-snapshot-ref",
        "remove-partition-specs",
        "remove-schemas",
    }
)
ALLOWED_REQUIREMENTS = frozenset(
    {
        "assert-create",
        "assert-table-uuid",
        "assert-ref-snapshot-id",
        "assert-last-assigned-field-id",
        "assert-current-schema-id",
        "assert-last-assigned-partition-id",
        "assert-default-spec-id",
        "assert-default-sort-order-id",
    }
)
MAX_FORMAT_VERSION = 2
_UPDATE_ADAPTER: TypeAdapter[Any] = TypeAdapter(TableUpdate)
_REQUIREMENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(TableRequirement)
S3A_PREFIX = f"{locations.SCHEME}://"


class IcebergError(Exception):
    """Erro de protocolo REST do Iceberg, devolvido como `ErrorModel`."""

    def __init__(self, status: int, error_type: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type
        self.message = message


def error_response(exc: IcebergError) -> JSONResponse:
    body = {"error": {"message": exc.message, "type": exc.error_type, "code": exc.status}}
    return JSONResponse(body, status_code=exc.status)


async def handle_error(_request: Request, exc: Exception) -> Response:
    assert isinstance(exc, IcebergError)
    return error_response(exc)


async def _authenticate(request: Request) -> RuntimeGrant:
    """Token (401) e depois Host (403), reaproveitando as dependências de runtime com o corpo `ErrorModel`."""
    try:
        grant = await require_runtime_token(request)
        await require_runtime_host(request)
    except HTTPException as exc:
        kind = "NotAuthorizedException" if exc.status_code == 401 else "ForbiddenException"
        message = "Não autorizado" if exc.status_code == 401 else "Host não permitido"
        raise IcebergError(exc.status_code, kind, message) from None
    return grant


Grant = Annotated[RuntimeGrant, Depends(_authenticate)]
router = APIRouter(prefix="/iceberg", dependencies=[Depends(_authenticate)])


def _no_such_namespace() -> IcebergError:
    return IcebergError(404, "NoSuchNamespaceException", "Namespace não encontrado")


def _no_such_table() -> IcebergError:
    return IcebergError(404, "NoSuchTableException", "Tabela não encontrada")


def _s3a_refused(message: str, commit: bool) -> IcebergError:
    """Recusa de gravação s3a: 409 só no commit; no create o 409 viraria AlreadyExistsException no cliente."""
    if commit:
        return IcebergError(409, "CommitFailedException", message)
    return _bad_request(message)


def parse_namespace(raw: str) -> str:
    """Namespace do protocolo (níveis separados por 0x1F) no formato pontuado do JdbcCatalog."""
    levels = raw.split(NAMESPACE_SEPARATOR)
    invalid = len(raw) > MAX_NAME_LENGTH or any(
        not level or "." in level or "\x00" in level for level in levels
    )
    if invalid:
        raise IcebergError(400, "BadRequestException", "Namespace inválido")
    return ".".join(levels)


def parse_table_name(raw: str) -> str:
    if not raw or len(raw) > MAX_NAME_LENGTH or "\x00" in raw:
        raise IcebergError(400, "BadRequestException", "Nome de tabela inválido")
    return raw


def _levels(namespace: str) -> list[str]:
    return namespace.split(".")


def _home(request: Request) -> Path:
    home: Path = request.app.state.settings.home
    return home


def _is_s3a(location: str) -> bool:
    return location.startswith(S3A_PREFIX)


class _Store:
    """Conexão do bucket notislake numa requisição; só é resolvida quando uma tabela `s3a` é tocada.

    `opener` serve a leitura de metadata. A gravação só vale com a conexão com que o kernel abriu.
    """

    def __init__(self, grant: RuntimeGrant, opener: iceberg_jdbc.StoreOpener) -> None:
        self.opener = opener
        self._grant = grant
        self._writer: objectstore.Connection | None = None

    def writer(self, commit: bool) -> objectstore.Connection:
        """Conexão para gravar; recusa (409 no commit, 400 no create) se o kernel abriu sem S3A ou a conexão difere."""
        if self._writer is not None:
            return self._writer
        expected = self._grant.s3a_fingerprint
        if expected is None:
            raise _s3a_refused("O kernel foi aberto sem conexão S3A; reinicie-o para gravar em s3a", commit)
        try:
            conn = self.opener()
        except ConfigInvalid:
            raise _s3a_refused("A configuração do notislake é inválida; corrija-a e reinicie o kernel", commit) from None
        except objectstore.Unavailable:
            raise _unavailable("O armazenamento notislake está indisponível", commit) from None
        if not hmac.compare_digest(expected, fingerprint(conn)):
            raise _s3a_refused("A conexão do notislake mudou depois da abertura do kernel; reinicie-o para gravar em s3a", commit)
        self._writer = conn
        return conn


def _store(request: Request, grant: RuntimeGrant) -> _Store:
    home = _home(request)
    supervisor = getattr(request.app.state, "notislake", None)
    return _Store(grant, lambda: objectstore.resolve_from_app(home, supervisor))


def _run_read[T](home: Path, func: Callable[[sqlite3.Connection, bool], T]) -> T:
    if not catalog_db_path(home).exists():
        raise IcebergError(503, "ServiceUnavailableException", "Catálogo ainda não inicializado")
    conn = connect(home)
    try:
        conn.execute("PRAGMA query_only=ON")
        try:
            has_type = iceberg_jdbc.check_schema(conn)
        except iceberg_jdbc.UnsupportedIcebergSchema:
            raise IcebergError(500, "ServiceFailureException", "Formato do catálogo Iceberg não suportado") from None
        return func(conn, has_type)
    finally:
        conn.close()


async def _read[T](request: Request, func: Callable[[sqlite3.Connection, bool], T]) -> T:
    try:
        return await asyncio.to_thread(_run_read, _home(request), func)
    except sqlite3.Error:
        raise IcebergError(503, "ServiceUnavailableException", "Catálogo ocupado ou indisponível") from None


def _require_namespace(conn: sqlite3.Connection, namespace: str) -> None:
    if not iceberg_jdbc.namespace_exists(conn, namespace):
        raise _no_such_namespace()


@router.get("/v1/config")
async def get_config() -> dict[str, Any]:
    """Sem `prefix`; `endpoints` explícito, porque o cliente trata a omissão como suporte a tudo.

    `io-impl` em `overrides` impõe `HadoopFileIO` ao cliente, que assim lê e grava `s3a://`.
    """
    return {"defaults": {}, "overrides": {"io-impl": HADOOP_FILE_IO}, "endpoints": list(ENDPOINTS)}


@router.get("/v1/namespaces")
async def list_namespaces(request: Request, parent: str | None = None) -> dict[str, Any]:
    parent_ns = parse_namespace(parent) if parent else None

    def query(conn: sqlite3.Connection, _has_type: bool) -> list[str]:
        if parent_ns is not None:
            _require_namespace(conn, parent_ns)
        return iceberg_jdbc.list_child_namespaces(conn, parent_ns)

    names = await _read(request, query)
    return {"namespaces": [_levels(n) for n in names]}


@router.get("/v1/namespaces/{namespace}")
async def load_namespace(request: Request, namespace: str) -> dict[str, Any]:
    ns = parse_namespace(namespace)

    def query(conn: sqlite3.Connection, _has_type: bool) -> dict[str, str]:
        _require_namespace(conn, ns)
        return iceberg_jdbc.namespace_properties(conn, ns)

    return {"namespace": _levels(ns), "properties": await _read(request, query)}


@router.head("/v1/namespaces/{namespace}")
async def namespace_exists(request: Request, namespace: str) -> Response:
    ns = parse_namespace(namespace)

    def query(conn: sqlite3.Connection, _has_type: bool) -> None:
        _require_namespace(conn, ns)

    await _read(request, query)
    return Response(status_code=204)


@router.get("/v1/namespaces/{namespace}/tables")
async def list_tables(request: Request, namespace: str) -> dict[str, Any]:
    ns = parse_namespace(namespace)

    def query(conn: sqlite3.Connection, has_type: bool) -> list[str]:
        _require_namespace(conn, ns)
        return iceberg_jdbc.list_table_names(conn, ns, has_type)

    names = await _read(request, query)
    return {"identifiers": [{"namespace": _levels(ns), "name": name} for name in names]}


def _disable_gc(metadata: dict[str, Any]) -> dict[str, Any]:
    """Devolve `gc.enabled=false` ao cliente em toda tabela: não há warehouse local e as de `s3a` não têm rename.

    O `SparkCatalog.purgeTable` (Iceberg 1.7.1) recusa o PURGE com essa propriedade, antes de qualquer drop; sem ela
    apagaria os arquivos no cliente, contornando `_drop_table`. Só vai na resposta: o metadata.json gravado e o CAS
    de `metadata_location` ficam intactos. Efeito: `expire_snapshots` e `remove_orphan_files` também são recusados.
    Aplicado no load e nas respostas de create direto e de commit; não na do stage-create, porque o cliente reenvia
    o metadata dele (com as propriedades) no commit `assert-create`, e a propriedade seria gravada no metadata.
    """
    properties = metadata.get("properties")
    metadata["properties"] = {**(properties if isinstance(properties, dict) else {}), "gc.enabled": "false"}
    return metadata


def _load_table(
    grant: RuntimeGrant, ns: str, table: str, store: _Store
) -> Callable[[sqlite3.Connection, bool], dict[str, Any]]:
    def query(conn: sqlite3.Connection, has_type: bool) -> dict[str, Any]:
        location = iceberg_jdbc.table_metadata_location(conn, ns, table, has_type)
        if location is None:
            raise _no_such_table()
        try:
            metadata = _read_raw_metadata(location, grant, store)
        except iceberg_jdbc.MetadataOutsideRoot:
            raise _outside_mounts() from None
        except iceberg_jdbc.MetadataStoreUnavailable:
            raise _unavailable("O armazenamento notislake está indisponível", False) from None
        except iceberg_jdbc.IcebergMetadataError:
            raise IcebergError(500, "ServiceFailureException", "Não foi possível ler o metadata da tabela") from None
        return {"metadata-location": location, "metadata": _disable_gc(metadata), "config": {}}

    return query


@router.get("/v1/namespaces/{namespace}/tables/{table}")
async def load_table(request: Request, namespace: str, table: str, grant: Grant) -> dict[str, Any]:
    return await _read(request, _load_table(grant, parse_namespace(namespace), parse_table_name(table), _store(request, grant)))


@router.head("/v1/namespaces/{namespace}/tables/{table}")
async def table_exists(request: Request, namespace: str, table: str) -> Response:
    ns, name = parse_namespace(namespace), parse_table_name(table)

    def query(conn: sqlite3.Connection, has_type: bool) -> None:
        if iceberg_jdbc.table_metadata_location(conn, ns, name, has_type) is None:
            raise _no_such_table()

    await _read(request, query)
    return Response(status_code=204)


@router.post("/v1/namespaces/{namespace}/tables/{table}/metrics")
async def report_metrics(namespace: str, table: str) -> Response:
    """Relatório de métricas do cliente: aceito e descartado."""
    return Response(status_code=204)




async def _json_body(request: Request) -> dict[str, Any]:
    """Corpo JSON (objeto) com teto de bytes, medido também sem Content-Length (chunked)."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        raise IcebergError(400, "BadRequestException", "Corpo da requisição grande demais")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise IcebergError(400, "BadRequestException", "Corpo da requisição grande demais")
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks) or b"{}")
    except (ValueError, RecursionError):
        raise IcebergError(400, "BadRequestException", "JSON inválido") from None
    if not isinstance(body, dict):
        raise IcebergError(400, "BadRequestException", "O corpo deve ser um objeto JSON")
    return body


def _bad_request(message: str) -> IcebergError:
    return IcebergError(400, "BadRequestException", message)


def _unavailable(message: str, commit: bool) -> IcebergError:
    """Falha transitória antes do CAS: 409 no commit (seguro repetir; 5xx viraria estado desconhecido), 503 nos demais."""
    if commit:
        return IcebergError(409, "CommitFailedException", f"{message}; tente o commit novamente")
    return IcebergError(503, "ServiceUnavailableException", message)


def _new_name(value: Any, what: str) -> str:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise _bad_request(f"{what} inválido: use letras, números, _, $ e - (até 128 caracteres)")
    return value


def _new_namespace(levels: Any) -> str:
    if not isinstance(levels, list) or not levels or len(levels) > 16:
        raise _bad_request("Namespace inválido")
    return ".".join(_new_name(level, "Nome de namespace") for level in levels)


def _identifier(value: Any, what: str) -> tuple[str, str]:
    if not isinstance(value, dict) or not isinstance(value.get("namespace"), list):
        raise _bad_request(f"{what} inválido")
    namespace = _new_namespace(value["namespace"])
    return namespace, _new_name(value.get("name"), "Nome de tabela")


def _string_map(value: Any, what: str) -> dict[str, str]:
    if value is None:
        return {}
    ok = isinstance(value, dict) and len(value) <= MAX_PROPERTIES
    if not ok or not all(isinstance(k, str) and isinstance(v, str) and len(k) <= 255 and len(v) <= 1000 for k, v in value.items()):
        raise _bad_request(f"{what} inválidas")
    return dict(value)


@contextmanager
def _write_txn(conn: sqlite3.Connection, begin_error: Callable[[], IcebergError] | None = None) -> Iterator[None]:
    """Transação de escrita; `begin_error` traduz a falha do `BEGIN IMMEDIATE` (nada aplicado ainda)."""
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.Error:
        if begin_error is None:
            raise
        raise begin_error() from None
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _run_write[T](home: Path, func: Callable[[sqlite3.Connection, bool], T], commit: bool) -> T:
    if not catalog_db_path(home).exists():
        raise _unavailable("Catálogo ainda não inicializado", commit)
    conn = connect(home)
    try:
        try:
            has_type = iceberg_jdbc.check_schema(conn)
        except iceberg_jdbc.UnsupportedIcebergSchema:
            raise IcebergError(422, "UnprocessableEntityException", "Formato do catálogo Iceberg não suportado") from None
        return func(conn, has_type)
    finally:
        conn.close()


async def _write[T](request: Request, func: Callable[[sqlite3.Connection, bool], T], *, commit: bool = False) -> T:
    """Roda `func` numa thread. Com `commit`, erro de SQLite que escapa é anterior ao CAS (o `_register` o traduz) e vira 409."""
    try:
        return await asyncio.to_thread(_run_write, _home(request), func, commit)
    except sqlite3.Error:
        raise _unavailable("Catálogo ocupado ou indisponível", commit) from None


def _outside_mounts() -> IcebergError:
    return IcebergError(
        403, "ForbiddenException", "A tabela fica fora das pastas montadas no container e do notislake e não é acessível ao runtime Docker"
    )


def _read_raw_metadata(location: str, grant: RuntimeGrant, store: _Store) -> dict[str, Any]:
    """`metadata.json` local (dentro das pastas montadas) ou em `s3a://notislake/...` (lido com teto)."""
    if not _is_s3a(location):
        return iceberg_jdbc.read_metadata_within(location, grant.roots)
    try:
        locations.parse_notislake(location)
    except locations.InvalidLocation:
        raise iceberg_jdbc.MetadataOutsideRoot("metadata outside the allowed roots") from None
    return iceberg_jdbc.read_metadata(location, store.opener)


def _table_path(location: str, grant: RuntimeGrant) -> Path:
    """Pasta local (realpath) de uma tabela externa nova ou escrita: estritamente dentro de uma pasta montada; 400 caso contrário.

    Só vê caminhos locais do usuário: a URI `s3a` é tratada por `_s3a_table` e nunca chega aqui.
    """
    path = local_path(location)
    if path is None:
        raise _bad_request("A location deve ser um caminho local")
    real = Path(os.path.realpath(path))
    for root in grant.roots:
        real_root = Path(os.path.realpath(root))
        if real != real_root and is_within(real, real_root):
            return real
    raise _bad_request("A location deve ficar numa pasta montada no container ou em s3a://notislake")


def _s3a_table(location: str) -> locations.NotislakeLocation:
    """Location `s3a://notislake/<camada>/<dataset>[/...]` de uma tabela; 400 se inválida ou fora do notislake.

    Só a forma é validada aqui; camada, nome e sobreposição dependem do catálogo (`_require_destination`).
    """
    try:
        return locations.parse_notislake(location)
    except locations.InvalidLocation:
        raise _bad_request("A location s3a deve ser s3a://notislake/<camada>/<dataset> sem segmentos vazios, '.' ou '..'") from None


def _table_target(location: str, grant: RuntimeGrant) -> Path | locations.NotislakeLocation:
    """Destino de uma tabela nova ou escrita: pasta local (`_table_path`) ou location `s3a` do notislake."""
    if _is_s3a(location):
        return _s3a_table(location)
    return _table_path(location, grant)


def _registered_folder(metadata_location: str) -> Path | locations.NotislakeLocation | None:
    """Pasta (local) ou prefixo (`s3a`) da tabela dona de `metadata_location`; `None` se não for reconhecível."""
    folder = iceberg_jdbc.table_folder(metadata_location)
    if folder is not None:
        return folder
    prefix = iceberg_jdbc.table_prefix(metadata_location)
    return locations.parse_notislake(prefix) if prefix is not None else None


def _notislake_uri(location: str) -> str | None:
    try:
        return locations.parse_notislake(location).uri
    except locations.InvalidLocation:
        return None


_DESTINATION_MESSAGES = {
    "schema_not_layer": "O namespace precisa ser uma camada do notislake (bronze, silver ou gold) para gravar em s3a",
    "outside_layer": "A location deve ficar dentro da camada do namespace",
    "overlaps_table": "A location se sobrepõe à pasta de outra tabela registrada",
    "too_shallow": "A location s3a deve ter ao menos <camada>/<dataset>",
    "bad_segment": "A location ou o nome da tabela tem segmento inválido",
    "not_notislake": "A location deve ficar no bucket notislake",
}


def _destination_refused(code: str) -> IcebergError:
    """400 com o código estável (`InvalidLocation.code` ou nome repetido) no fim da mensagem, para o hook reconhecê-lo."""
    return _bad_request(f"{_DESTINATION_MESSAGES.get(code, 'Destino da tabela recusado')} ({code})")


def _require_free_name(conn: sqlite3.Connection, ns: str, table: str) -> None:
    """400 se `<ns>.<t>` já existe no registro Delta/Parquet (as duas pastas coincidiriam no notislake)."""
    if table_name_exists(conn, ns, table):
        raise _bad_request(f"A tabela já existe no catálogo spark_catalog ({ERR_NAME_IN_OTHER_CATALOG})")


def _require_no_overlap(conn: sqlite3.Connection, folder: Path | None) -> None:
    """400 se a pasta local `folder` é ancestral ou descendente (sem diferenciar caixa) da pasta de outra tabela registrada.

    Vale para tabelas Iceberg e para locations Delta/Parquet do registro; outro dono da pasta perderia dados no purge.
    """
    if folder is None:
        return
    others = [iceberg_jdbc.table_folder(m) for m in iceberg_jdbc.all_metadata_locations(conn)]
    others += [local_path(loc) for loc in all_table_locations(conn)]
    for other in others:
        if other is not None:
            real_other = Path(os.path.realpath(other))
            if is_within(real_other, folder, fold=True) or is_within(folder, real_other, fold=True):
                raise _bad_request("A location se sobrepõe à pasta de outra tabela registrada")


def _require_exact_layer_case(ns: str) -> None:
    """400 se `ns` é uma camada só na caixa (`Bronze`): no JdbcCatalog ele vira pasta própria, fora das camadas."""
    if locations.is_layer_case_variant(ns):
        raise _destination_refused("schema_not_layer")


def _require_destination(
    conn: sqlite3.Connection, ns: str, table: str, target: Path | locations.NotislakeLocation, own: str | None = None
) -> None:
    """Recusa (400) antes de gravar: nome já usado no outro catálogo e destino fora da regra da camada.

    Em `s3a` vale `locations.table_destination` (camada pelo namespace, sem sobrepor outra tabela; `own` é a pasta da
    própria tabela, ignorada); em pasta local, a checagem de sobreposição local.
    """
    _require_free_name(conn, ns, table)
    if not isinstance(target, locations.NotislakeLocation):
        _require_no_overlap(conn, target)
        return
    _require_exact_layer_case(ns)
    try:
        locations.table_destination(ns, table, target.uri, iceberg_jdbc.known_table_locations(conn), own)
    except locations.InvalidLocation as exc:
        raise _destination_refused(exc.code) from None


def _remove_quiet(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        log.warning("não foi possível remover um metadata.json não registrado")


def _file_uri(path: Path) -> str:
    """Forma `file:/abs` do Hadoop, a mesma que o JdbcCatalog do runtime local grava."""
    return f"file:{path}"


def _next_version(previous_location: str | None) -> int:
    match = re.match(r"(\d+)-", Path(previous_location or "").name)
    return int(match.group(1)) + 1 if match else 0


def _remove_remote_quiet(conn: objectstore.Connection, key: str) -> None:
    """Remove só o objeto `key` (nunca por prefixo); falha vira aviso."""
    try:
        objectstore.delete_key(conn, key)
    except objectstore.ObjectStoreError:
        log.warning("não foi possível remover um metadata.json não registrado do bucket")


def _write_remote_metadata(
    table: locations.NotislakeLocation, name: str, data: bytes, store: _Store, commit: bool
) -> tuple[Callable[[], None], str, bytes]:
    """Grava `<prefixo>/metadata/<name>` no bucket por criação exclusiva, só com a conexão validada pelo fingerprint."""
    conn = store.writer(commit)
    key = f"{table.key}/metadata/{name}"
    try:
        objectstore.put_exclusive(conn, key, data)
    except objectstore.ObjectStoreError:
        raise _unavailable("Não foi possível gravar o metadata da tabela", commit) from None
    return (lambda: _remove_remote_quiet(conn, key)), f"{table.uri}/metadata/{name}", data


def _write_metadata_file(
    metadata: TableMetadata, grant: RuntimeGrant, previous_location: str | None, commit: bool, store: _Store
) -> tuple[Callable[[], None], str, bytes]:
    """Grava o `metadata.json` novo (nome único, criação exclusiva). Devolve a remoção do arquivo, a URI e o conteúdo.

    Grava sempre em `<location>/metadata/`, no disco ou no bucket (`s3a`). Levanta 400 (location recusada / grande demais)
    ou, na falha de E/S, 409 no commit e 503 no create; nada é registrado aqui e o arquivo parcial é removido.
    """
    data = metadata.model_dump_json().encode("utf-8")
    if len(data) > iceberg_jdbc.MAX_METADATA_BYTES:
        raise _bad_request("O metadata resultante excede o limite suportado")
    destination = _table_target(metadata.location, grant)
    name = f"{_next_version(previous_location):05d}-{uuid.uuid4()}.metadata.json"
    if isinstance(destination, locations.NotislakeLocation):
        return _write_remote_metadata(destination, name, data, store, commit)
    table_dir = destination
    target = table_dir / "metadata" / name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not is_within(Path(os.path.realpath(target.parent)), table_dir):  # `metadata/` é symlink para fora da tabela
            raise _bad_request("A pasta metadata da tabela não pode ser um link para fora da location")
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except OSError:
        raise _unavailable("Não foi possível gravar o metadata da tabela", commit) from None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        _remove_quiet(target)
        raise _unavailable("Não foi possível gravar o metadata da tabela", commit) from None
    return (lambda: _remove_quiet(target)), _file_uri(target), data


def _parse_updates(raw: Any) -> tuple[Any, ...]:
    if not isinstance(raw, list) or len(raw) > MAX_UPDATES:
        raise _bad_request("Lista de atualizações inválida")
    parsed = []
    for item in raw:
        action = item.get("action") if isinstance(item, dict) else None
        if action not in ALLOWED_ACTIONS:
            raise _bad_request("Atualização de tabela não suportada")
        try:
            parsed.append(_UPDATE_ADAPTER.validate_python(item))
        except ValidationError:
            raise _bad_request(f"Atualização '{action}' inválida") from None
    return tuple(parsed)


def _parse_requirements(raw: Any) -> tuple[Any, ...]:
    if not isinstance(raw, list) or len(raw) > MAX_UPDATES:
        raise _bad_request("Lista de requisitos inválida")
    parsed = []
    for item in raw:
        kind = item.get("type") if isinstance(item, dict) else None
        if kind not in ALLOWED_REQUIREMENTS:
            raise _bad_request("Requisito de tabela não suportado")
        try:
            parsed.append(_REQUIREMENT_ADAPTER.validate_python(item))
        except ValidationError:
            raise _bad_request(f"Requisito '{kind}' inválido") from None
    return tuple(parsed)


def _check_updates(updates: tuple[Any, ...], grant: RuntimeGrant) -> None:
    for update in updates:
        if isinstance(update, UpgradeFormatVersionUpdate) and update.format_version > MAX_FORMAT_VERSION:
            raise _bad_request("format-version acima de 2 não é suportado")
        if isinstance(update, SetLocationUpdate):
            _table_target(update.location, grant)


def _check_data_paths(properties: dict[str, str], location: str) -> None:
    """400 se algum caminho de dados aponta para fora da pasta da própria tabela ou há location provider customizado.

    Outra tabela gravando dentro da pasta de A perderia os dados no purge de A (comparação com realpath e fold).
    `write.location-provider.impl` carrega classe que escolhe caminhos arbitrários, então é sempre recusado.
    """
    if LOCATION_PROVIDER_PROPERTY in properties:
        raise _bad_request(f"{LOCATION_PROVIDER_PROPERTY} não é suportado")
    own = local_path(location)
    for key in DATA_PATH_PROPERTIES:
        value = properties.get(key)
        if value is None:
            continue
        if _is_s3a(location):
            if not locations.within(value, location):
                raise _bad_request(f"{key} deve ficar dentro da location da própria tabela")
            continue
        path = local_path(value)
        if own is None or path is None or not is_within(Path(os.path.realpath(path)), Path(os.path.realpath(own)), fold=True):
            raise _bad_request(f"{key} deve ficar dentro da location da própria tabela")


def _empty_metadata() -> TableMetadata:
    """Base vazia para aplicar as atualizações de uma criação (V1 só até o `upgrade-format-version`)."""
    return TableMetadataV1.model_construct(last_column_id=-1, schema=Schema())


def _load_current(location: str, grant: RuntimeGrant, store: _Store) -> TableMetadata:
    try:
        raw = _read_raw_metadata(location, grant, store)
    except iceberg_jdbc.MetadataOutsideRoot:
        raise _outside_mounts() from None
    except iceberg_jdbc.MetadataStoreUnavailable:
        raise _unavailable("O armazenamento notislake está indisponível", False) from None
    except iceberg_jdbc.IcebergMetadataError:
        raise IcebergError(422, "UnprocessableEntityException", "Não foi possível ler o metadata da tabela") from None
    try:
        metadata = TableMetadataUtil.parse_obj(raw)
    except (ValidationError, ValueError, TypeError):
        raise IcebergError(422, "UnprocessableEntityException", "O metadata atual da tabela não é suportado pelo servidor") from None
    if isinstance(metadata, TableMetadataV3):
        raise IcebergError(422, "UnprocessableEntityException", "Tabelas com format-version 3 não são suportadas")
    return metadata


def _result(metadata_location: str | None, data: bytes, *, guard: bool = True) -> dict[str, Any]:
    metadata = json.loads(data)
    result: dict[str, Any] = {"metadata": _disable_gc(metadata) if guard else metadata, "config": {}}
    if metadata_location is not None:
        result["metadata-location"] = metadata_location
    return result


def _register(
    conn: sqlite3.Connection, has_type: bool, ns: str, table: str, previous: str | None, new_location: str, commit: bool
) -> bool:
    """CAS (ou INSERT na criação) numa transação curta; `False` se perdeu a disputa.

    Falha do `BEGIN IMMEDIATE` (nada aplicado): 409 no commit e 503 no create. Na criação, nome repetido no outro
    catálogo, camada errada ou sobreposição de pasta: 400. Qualquer outra falha depois dele: 500.
    """
    try:
        with _write_txn(conn, lambda: _unavailable("Catálogo ocupado ou indisponível", commit)):
            if previous is None:
                folder = _registered_folder(new_location)
                if folder is not None:
                    _require_destination(conn, ns, table, folder)
                return iceberg_jdbc.insert_table(conn, ns, table, new_location, has_type)
            return iceberg_jdbc.swap_metadata_location(conn, ns, table, previous, new_location, has_type)
    except sqlite3.Error:
        raise IcebergError(500, "CommitStateUnknownException", "Falha ao registrar o commit no catálogo") from None


def _persist(
    conn: sqlite3.Connection,
    has_type: bool,
    grant: RuntimeGrant,
    ns: str,
    table: str,
    metadata: TableMetadata,
    previous: str | None,
    store: _Store,
    *,
    commit: bool,
) -> dict[str, Any]:
    """Grava o metadata novo, registra (CAS) e, se perdeu, apaga o arquivo e responde 409."""
    if previous is None:  # checagem prévia, antes de criar `metadata/` na pasta; a definitiva é a de `_register`
        _require_destination(conn, ns, table, _table_target(metadata.location, grant))
    remove_file, location, data = _write_metadata_file(metadata, grant, previous, commit, store)
    try:
        registered = _register(conn, has_type, ns, table, previous, location, commit)
    except IcebergError as exc:
        if exc.status != 500:  # com 500 o estado é desconhecido: o arquivo pode estar referenciado
            remove_file()
        raise
    except BaseException:
        remove_file()
        raise
    if not registered:
        remove_file()
        if previous is None:
            raise IcebergError(409, "AlreadyExistsException", "A tabela já existe")
        raise IcebergError(409, "CommitFailedException", "A tabela foi alterada por outro commit")
    return _result(location, data)


def _default_location(ns: str, table: str) -> str:
    """Location padrão MANAGED `s3a://notislake/<camada>/<t>`; 400 se o namespace não é uma camada."""
    _require_exact_layer_case(ns)
    try:
        return locations.managed_location(ns, table)
    except locations.InvalidLocation as exc:
        raise _destination_refused(exc.code) from None


def _create_table(grant: RuntimeGrant, ns: str, body: dict[str, Any], store: _Store) -> Callable[[sqlite3.Connection, bool], dict[str, Any]]:
    _new_namespace(ns.split("."))
    table = _new_name(body.get("name"), "Nome de tabela")
    properties = _string_map(body.get("properties"), "Propriedades")
    version = properties.get("format-version", "2")
    if version not in ("1", "2"):
        raise _bad_request("format-version acima de 2 não é suportado")
    location = body.get("location")
    if location is not None and not isinstance(location, str):
        raise _bad_request("location inválida")
    final_location = location or _default_location(ns, table)
    _table_target(final_location, grant)
    _check_data_paths(properties, final_location)
    try:
        schema = Schema.model_validate(body.get("schema"))
        spec = PartitionSpec.model_validate(body["partition-spec"]) if body.get("partition-spec") else UNPARTITIONED_PARTITION_SPEC
        order = SortOrder.model_validate(body["write-order"]) if body.get("write-order") else UNSORTED_SORT_ORDER
        metadata = new_table_metadata(schema, spec, order, final_location, properties)
    except (ValidationError, ValueError, TypeError, KeyError):
        raise _bad_request("Schema, partição ou ordenação inválidos") from None
    staged = body.get("stage-create") is True

    def run(conn: sqlite3.Connection, has_type: bool) -> dict[str, Any]:
        if not iceberg_jdbc.namespace_exists(conn, ns):
            raise _no_such_namespace()
        if iceberg_jdbc.table_row_exists(conn, ns, table, ignore_case=True):  # APFS: `T` e `t` são a mesma pasta
            raise IcebergError(409, "AlreadyExistsException", "A tabela já existe")
        if staged:  # CTAS: o cliente grava os dados antes do commit, então a recusa tem de vir já aqui
            _require_destination(conn, ns, table, _table_target(final_location, grant))
            return _result(None, metadata.model_dump_json().encode("utf-8"), guard=False)
        return _persist(conn, has_type, grant, ns, table, metadata, None, store, commit=False)

    return run


def _commit_table(
    grant: RuntimeGrant, ns: str, table: str, body: dict[str, Any], store: _Store
) -> Callable[[sqlite3.Connection, bool], dict[str, Any]]:
    requirements = _parse_requirements(body.get("requirements", []))
    updates = _parse_updates(body.get("updates", []))
    _check_updates(updates, grant)
    creating = any(isinstance(r, AssertCreate) for r in requirements)
    if creating:  # CTAS vira pasta como o create direto: mesmas regras de nome
        _new_name(table, "Nome de tabela")
        _new_namespace(ns.split("."))

    def run(conn: sqlite3.Connection, has_type: bool) -> dict[str, Any]:
        location = iceberg_jdbc.table_metadata_location(conn, ns, table, has_type)
        if location is None and not creating:
            raise _no_such_table()
        if location is not None and creating:
            raise IcebergError(409, "AlreadyExistsException", "A tabela já existe")
        if location is None and not iceberg_jdbc.namespace_exists(conn, ns):
            raise _no_such_namespace()
        if location is None and iceberg_jdbc.table_row_exists(conn, ns, table, ignore_case=True):
            raise IcebergError(409, "AlreadyExistsException", "Já existe uma tabela ou view com esse nome")
        if location == "":
            raise IcebergError(422, "UnprocessableEntityException", "A tabela não tem metadata registrado")
        if location and _is_s3a(location):  # recusa antes de ler: conexão divergente ou kernel sem S3A
            store.writer(commit=True)
        base = _load_current(location, grant, store) if location else None
        for requirement in requirements:
            try:
                requirement.validate(base)
            except CommitFailedException:
                raise IcebergError(409, "CommitFailedException", f"Requisito não atendido: {requirement.type}") from None
        if base is not None:  # a pasta antiga deixaria de ser protegida no purge e os write.*.path gravados não seriam reavaliados
            for update in updates:
                if isinstance(update, SetLocationUpdate) and update.location.rstrip("/") != base.location.rstrip("/"):
                    raise _bad_request("Alterar a location de uma tabela existente não é suportado")
        try:
            new = update_table_metadata(
                base or _empty_metadata(), updates, enforce_validation=base is None, metadata_location=location or None
            )
        except Exception as exc:  # noqa: BLE001 - o pyiceberg levanta ValueError, ValidationError e exceções próprias
            log.info("atualização de metadata recusada: %s", type(exc).__name__)
            raise IcebergError(422, "UnprocessableEntityException", "As atualizações não puderam ser aplicadas à tabela") from None
        if isinstance(new, TableMetadataV3) or new.format_version > MAX_FORMAT_VERSION:
            raise _bad_request("format-version acima de 2 não é suportado")
        _check_data_paths(new.properties, new.location)
        return _persist(conn, has_type, grant, ns, table, new, location or None, store, commit=True)

    return run


def _require_inside_roots(location: str, grant: RuntimeGrant) -> None:
    """403 se o metadata da tabela está fora das pastas montadas e do notislake (como load/commit)."""
    if _is_s3a(location):
        if _notislake_uri(location) is None:
            raise _outside_mounts()
        return
    if not iceberg_jdbc.location_within_roots(location, grant.roots):
        raise _outside_mounts()


def _drop_table(
    grant: RuntimeGrant, ns: str, table: str, purge: bool
) -> Callable[[sqlite3.Connection, bool], None]:
    def run(conn: sqlite3.Connection, has_type: bool) -> None:
        location = iceberg_jdbc.table_metadata_location(conn, ns, table, has_type)
        if location is None:
            raise _no_such_table()
        if location:
            _require_inside_roots(location, grant)
        if purge and location and _is_s3a(location):  # S3 não tem rename: nada de `s3a` é apagado
            raise _bad_request("O purge de tabelas em s3a não é suportado: o purge foi recusado e nada foi removido")
        # Sem warehouse local, nenhuma tabela é apagada pelo backend: o purge de tabela local só remove a linha.
        with _write_txn(conn):
            if not iceberg_jdbc.delete_table_row(conn, ns, table, has_type):
                raise _no_such_table()

    return run


@router.post("/v1/namespaces")
async def create_namespace(request: Request) -> dict[str, Any]:
    body = await _json_body(request)
    ns = _new_namespace(body.get("namespace"))
    _require_exact_layer_case(ns)
    properties = _string_map(body.get("properties"), "Propriedades")
    if "exists" in properties:
        raise _bad_request("A propriedade 'exists' é reservada")

    def run(conn: sqlite3.Connection, _has_type: bool) -> None:
        with _write_txn(conn):
            if not iceberg_jdbc.create_namespace(conn, ns):
                raise IcebergError(409, "AlreadyExistsException", "O namespace já existe")
            iceberg_jdbc.set_namespace_properties(conn, ns, properties)

    await _write(request, run)
    return {"namespace": _levels(ns), "properties": properties}


@router.delete("/v1/namespaces/{namespace}")
async def drop_namespace(request: Request, namespace: str) -> Response:
    ns = parse_namespace(namespace)
    if ns in locations.LAYERS:  # grafia exata: `Bronze` legado não é camada no Iceberg e precisa poder sair
        raise IcebergError(403, "ForbiddenException", f"As camadas do notislake não podem ser excluídas ({CANNOT_DROP_LAYER})")

    def run(conn: sqlite3.Connection, has_type: bool) -> None:
        with _write_txn(conn):
            if not iceberg_jdbc.namespace_exists(conn, ns):
                raise _no_such_namespace()
            if iceberg_jdbc.has_child_namespaces(conn, ns) or iceberg_jdbc.namespace_entries(conn, ns, has_type):
                raise IcebergError(409, "NamespaceNotEmptyException", "O namespace não está vazio")
            iceberg_jdbc.drop_namespace_rows(conn, ns)

    await _write(request, run)
    return Response(status_code=204)


@router.post("/v1/namespaces/{namespace}/properties")
async def update_namespace_properties(request: Request, namespace: str) -> dict[str, Any]:
    ns = parse_namespace(namespace)
    body = await _json_body(request)
    updates = _string_map(body.get("updates"), "Propriedades")
    removals = body.get("removals") or []
    if not isinstance(removals, list) or not all(isinstance(k, str) and len(k) <= 255 for k in removals):
        raise _bad_request("Remoções inválidas")
    if "exists" in updates or "exists" in removals or set(updates) & set(removals):
        raise _bad_request("Propriedades inválidas")

    def run(conn: sqlite3.Connection, _has_type: bool) -> dict[str, Any]:
        with _write_txn(conn):
            if not iceberg_jdbc.namespace_exists(conn, ns):
                raise _no_such_namespace()
            removed: list[str] = []
            missing: list[str] = []
            for key in removals:
                (removed if iceberg_jdbc.remove_namespace_property(conn, ns, key) else missing).append(key)
            iceberg_jdbc.set_namespace_properties(conn, ns, updates)
        return {"updated": sorted(updates), "removed": removed, "missing": missing}

    return await _write(request, run)


@router.post("/v1/namespaces/{namespace}/tables")
async def create_table(request: Request, namespace: str, grant: Grant) -> dict[str, Any]:
    ns = parse_namespace(namespace)
    return await _write(request, _create_table(grant, ns, await _json_body(request), _store(request, grant)))


@router.post("/v1/namespaces/{namespace}/tables/{table}")
async def commit_table(request: Request, namespace: str, table: str, grant: Grant) -> dict[str, Any]:
    ns, name = parse_namespace(namespace), parse_table_name(table)
    result = await _write(request, _commit_table(grant, ns, name, await _json_body(request), _store(request, grant)), commit=True)
    result.pop("config", None)
    return result


@router.delete("/v1/namespaces/{namespace}/tables/{table}")
async def drop_table(request: Request, namespace: str, table: str, grant: Grant, purgeRequested: bool = False) -> Response:
    ns, name = parse_namespace(namespace), parse_table_name(table)
    await _write(request, _drop_table(grant, ns, name, purgeRequested))
    return Response(status_code=204)


@router.post("/v1/tables/rename")
async def rename_table(request: Request, grant: Grant) -> Response:
    body = await _json_body(request)
    source = _identifier(body.get("source"), "Origem")
    target = _identifier(body.get("destination"), "Destino")

    def run(conn: sqlite3.Connection, has_type: bool) -> None:
        current = iceberg_jdbc.table_metadata_location(conn, source[0], source[1], has_type)
        if current:
            _require_inside_roots(current, grant)
        with _write_txn(conn):
            if iceberg_jdbc.table_metadata_location(conn, source[0], source[1], has_type) is None:
                raise _no_such_table()
            if not iceberg_jdbc.namespace_exists(conn, target[0]):
                raise _no_such_namespace()
            if iceberg_jdbc.table_row_exists(conn, target[0], target[1]):
                raise IcebergError(409, "AlreadyExistsException", "O destino já existe")
            prefix = iceberg_jdbc.table_prefix(current) if current and _is_s3a(current) else None
            if prefix is None:
                _require_free_name(conn, target[0], target[1])
            else:  # a pasta não muda no rename: o novo nome precisa continuar numa camada válida
                try:
                    prefix_location = locations.parse_notislake(prefix)
                except locations.InvalidLocation as exc:
                    raise _destination_refused(exc.code) from None
                _require_destination(conn, target[0], target[1], prefix_location, own=prefix)
            if not iceberg_jdbc.rename_table_row(conn, source, target, has_type):
                raise _no_such_table()

    await _write(request, run)
    return Response(status_code=204)


@router.post("/v1/namespaces/{namespace}/register")
@router.post("/v1/transactions/commit")
async def refuse_unsupported() -> Response:
    raise IcebergError(403, "ForbiddenException", NOT_SUPPORTED_MESSAGE)


@router.api_route("/{rest:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"])
async def not_found() -> Response:
    raise IcebergError(404, "NoSuchRouteException", "Rota não encontrada")
