"""Leitura e escrita de schemas do registro `nb_*` (Delta/Parquet/Hudi do `spark_catalog`) sem SparkSession.

As tabelas continuam escritas pelo módulo oculto do kernel; o backend só cria/remove schemas inteiros
(`create_namespace`/`drop_namespace`). A conexão e a transação (`BEGIN IMMEDIATE`) pertencem ao chamador.
Toda escrita sobe `nb_meta.generation`, que é o que faz as sessões abertas reconciliarem.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ..notislake import locations

SPARK_CATALOG = "spark_catalog"
DEFAULT_DATABASE = "default"
# Teto da varredura: tabelas por database e no total. Estourar o teto marca `"truncated": true`.
MAX_TABLES = 500
MAX_TOTAL_TABLES = 2000
MAX_DELETE_ATTEMPTS = 5  # tentativas de exclusão pelo kernel; depois a linha fica na fila, sem ser entregue
# Recusa por nome repetido: `<schema>.<t>` já existe no outro catálogo (Delta e Iceberg cairiam na mesma pasta do notislake).
ERR_NAME_IN_OTHER_CATALOG = "name_in_other_catalog"


def _bump_generation(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE nb_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'generation'")


def namespace_exists(conn: sqlite3.Connection, namespace: str) -> bool:
    """`default` sempre existe; os demais, por linha em `nb_namespaces` ou `nb_tables`. Sem distinção de caixa."""
    key = namespace.lower()
    if key == DEFAULT_DATABASE:
        return True
    row = conn.execute(
        "SELECT 1 FROM nb_namespaces WHERE catalog_name = ? AND lower(namespace) = ? "
        "UNION SELECT 1 FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ? LIMIT 1",
        (SPARK_CATALOG, key, SPARK_CATALOG, key),
    ).fetchone()
    return row is not None


def create_namespace(conn: sqlite3.Connection, namespace: str) -> bool:
    """Registra o schema em minúsculas (como o SessionCatalog); `False` se já existe. Dentro de transação."""
    key = namespace.lower()
    if namespace_exists(conn, key):
        return False
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # A location é a do schema no bucket reservado; o hook a usa ao hidratar a sessão (`CREATE DATABASE ... LOCATION`).
    conn.execute(
        "INSERT INTO nb_namespaces (catalog_name, namespace, location, created_at) VALUES (?, ?, ?, ?)",
        (SPARK_CATALOG, key, locations.schema_location(key, "s3"), stamp),
    )
    _bump_generation(conn)
    return True


def namespace_tables(conn: sqlite3.Connection, namespace: str) -> list[tuple[str, str, str]]:
    """`(table_name, location, table_type)` das tabelas do schema, ordenadas."""
    rows = conn.execute(
        "SELECT table_name, location, table_type FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ? "
        "ORDER BY table_name",
        (SPARK_CATALOG, namespace.lower()),
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def table_name_exists(conn: sqlite3.Connection, namespace: str, table: str) -> bool:
    """Existe `namespace.table` no registro `nb_tables`, sem distinção de caixa (colisão com o catálogo Iceberg)."""
    row = conn.execute(
        "SELECT 1 FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = lower(?) AND lower(table_name) = lower(?)",
        (SPARK_CATALOG, namespace, table),
    ).fetchone()
    return row is not None


def pending_locations(conn: sqlite3.Connection) -> list[str]:
    """Pastas na fila de exclusão: uma tabela não pode ser criada sobre elas (`pending_cleanup`)."""
    if not has_pending_table(conn):
        return []
    return [r[0] for r in conn.execute("SELECT location FROM nb_pending_deletions ORDER BY id")]


def all_table_locations(conn: sqlite3.Connection) -> list[str]:
    """Locations de todas as tabelas do registro (para checar se uma pasta ainda é usada)."""
    return [r[0] for r in conn.execute("SELECT location FROM nb_tables WHERE catalog_name = ?", (SPARK_CATALOG,))]


def drop_namespace(conn: sqlite3.Connection, namespace: str) -> None:
    """Remove as linhas de tabelas e do schema (cascade) e sobe a generation. Dentro de transação."""
    key = namespace.lower()
    conn.execute("DELETE FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ?", (SPARK_CATALOG, key))
    conn.execute("DELETE FROM nb_namespaces WHERE catalog_name = ? AND lower(namespace) = ?", (SPARK_CATALOG, key))
    _bump_generation(conn)


def local_path(location: str | None) -> Path | None:
    """Caminho local de uma URI `file:` ou caminho absoluto; `None` para outros esquemas (s3a, hdfs...)."""
    if not location:
        return None
    if location.startswith("file:"):
        return Path(unquote(urlparse(location).path))
    if "://" in location:
        return None
    path = Path(location)
    return path if path.is_absolute() else None


def is_available(location: str | None) -> bool | None:
    """`True`/`False` pelo stat do caminho local; `None` quando o local não é um caminho do disco."""
    path = local_path(location)
    if path is None:
        return None
    try:
        return path.exists()
    except OSError:
        return False


def _table_node(namespace: str, name: str, fmt: str, table_type: str, location: str, description: str | None) -> dict[str, Any]:
    return {
        "name": name,
        "namespace": [namespace],
        "format": fmt,
        "table_type": table_type,
        "is_temporary": False,
        "location": location,
        "available": is_available(location),
        "description": description,
    }


def _display_names(conn: sqlite3.Connection) -> set[str]:
    """Schemas exibidos: os com tabela de qualquer formato e os registrados em `nb_namespaces`.

    O `default` só aparece quando tem tabela; vazio, é omitido.
    """
    with_tables = {r[0] for r in conn.execute("SELECT DISTINCT namespace FROM nb_tables WHERE catalog_name = ?", (SPARK_CATALOG,))}
    registered = {
        r[0] for r in conn.execute("SELECT namespace FROM nb_namespaces WHERE catalog_name = ?", (SPARK_CATALOG,))
    } - {DEFAULT_DATABASE}
    return {*with_tables, *registered}


def empty_display_names() -> list[str]:
    """Schemas do `spark_catalog` sem `catalog.db`: nenhum, pois um catalog.db novo é quem semeia os iniciais."""
    return []


def list_databases(conn: sqlite3.Connection, max_total: int) -> tuple[list[dict[str, Any]], int]:
    """Databases do `spark_catalog` (todos os formatos) e o total de tabelas listadas.

    `max_total` é o que resta do teto global; databases após o teto voltam vazios e `truncated`.
    A regra de exibição está em `_display_names`.
    """
    names = _display_names(conn)
    ordered = sorted(names, key=lambda n: (n != DEFAULT_DATABASE, n))
    used = 0
    databases: list[dict[str, Any]] = []
    for db in ordered:
        if used >= max_total:
            databases.append({"name": db, "tables": [], "truncated": True})
            continue
        limit = min(MAX_TABLES, max_total - used)
        rows = conn.execute(
            "SELECT table_name, format, table_type, location, description FROM nb_tables "
            "WHERE catalog_name = ? AND namespace = ? ORDER BY table_name LIMIT ?",
            (SPARK_CATALOG, db, limit + 1),
        ).fetchall()
        entry: dict[str, Any] = {"name": db, "tables": [_table_node(db, *r) for r in rows[:limit]]}
        if len(rows) > limit:
            entry["truncated"] = True
        used += len(entry["tables"])
        databases.append(entry)
    return databases, used


def catalog_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Contagens exatas do `spark_catalog` (sem `MAX_TABLES`/`MAX_TOTAL_TABLES`): por namespace e por formato.

    Os namespaces vêm de `_display_names`. O `spark_catalog` não tem views no registro.
    """
    per_namespace: dict[str, int] = {}
    formats: dict[str, int] = {}
    for namespace, fmt, count in conn.execute(
        "SELECT namespace, format, COUNT(*) FROM nb_tables WHERE catalog_name = ? GROUP BY namespace, format",
        (SPARK_CATALOG,),
    ):
        per_namespace[namespace] = per_namespace.get(namespace, 0) + int(count)
        formats[fmt] = formats.get(fmt, 0) + int(count)
    names = _display_names(conn)
    ordered = sorted(names, key=lambda n: (n != DEFAULT_DATABASE, n))
    return {
        "namespaces": [{"name": ns, "tables": per_namespace.get(ns, 0), "views": 0} for ns in ordered],
        "tables": sum(per_namespace.get(ns, 0) for ns in names),
        "views": 0,
        "formats": formats,
    }


def _decode_columns(raw: str, partitions: set[str]) -> list[dict[str, Any]]:
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("columns_json is not a list")  # noqa: TRY004 — callers tratam ValueError; trocar o tipo mudaria o contrato
    return [
        {
            "name": str(c["name"]),
            "data_type": str(c.get("data_type", "")),
            "nullable": bool(c.get("nullable", True)),
            "is_partition": bool(c.get("is_partition")) or str(c["name"]) in partitions,
            "is_bucket": False,
            "description": c.get("description"),
        }
        for c in items
    ]


def _columns_or_empty(columns_json: str, partition_cols: str) -> list[dict[str, Any]]:
    try:
        partitions = {str(p) for p in json.loads(partition_cols)}
        return _decode_columns(columns_json, partitions)
    except (ValueError, KeyError, TypeError):
        # Registro com JSON ilegível: a tabela existe, só não há colunas para mostrar.
        return []


def _partition_names(partition_cols: str) -> list[str]:
    try:
        items = json.loads(partition_cols)
    except ValueError:
        return []
    return [str(p) for p in items] if isinstance(items, list) else []


def read_table_info(conn: sqlite3.Connection, database: str, table: str) -> dict[str, Any] | None:
    """Metadados de uma tabela Delta/Parquet/Hudi só do registro `nb_tables` (sem ler `_delta_log`/`.hoodie`).

    `None` se a tabela não existir. Nomes sem distinção de caixa.
    """
    row = conn.execute(
        "SELECT namespace, table_name, format, location, table_type, columns_json, partition_cols, description, "
        "created_at, updated_at, delta_version, hudi_instant FROM nb_tables "
        "WHERE catalog_name = ? AND namespace = ? COLLATE NOCASE AND table_name = ? COLLATE NOCASE",
        (SPARK_CATALOG, database, table),
    ).fetchone()
    if row is None:
        return None
    namespace, name, fmt, location, table_type, columns_json, partition_cols, description, created, updated, dv, hi = row
    version: dict[str, Any] | None = None
    if fmt == "delta":
        version = {"kind": "delta_version", "value": dv}
    elif fmt == "hudi":
        version = {"kind": "hudi_instant", "value": hi}
    return {
        "catalog": SPARK_CATALOG,
        "database": namespace,
        "table": name,
        "format": fmt,
        "table_type": table_type,
        # O DROP de uma MANAGED enfileira a pasta (`apply_plan` -> `nb_pending_deletions`) salvo se outra tabela a usa.
        "drop_behavior": "deletes_files" if table_type == "MANAGED" else "registry_only",
        "location": location,
        "available": is_available(location),
        "description": description,
        "created_at": created,
        "updated_at": updated,
        "partition_columns": _partition_names(partition_cols),
        "columns": _columns_or_empty(columns_json, partition_cols),
        "version": version,
        "history": None,
        "properties": None,
        "stats": None,
        "metadata_error": None,
    }


# As funções abaixo são injetadas no kernel por `inspect.getsource` (hook local e HTTP): só usam
# `json`/`sqlite3` e não têm anotações, que exigiriam nomes ausentes no kernel.
def read_snapshot(conn):
    """`(generation, rows, namespaces)` do `spark_catalog`; `rows` por `(db, tabela)` com os campos que o hook usa
    e `namespaces` como `{schema: location ou None}`."""
    row = conn.execute("SELECT value FROM nb_meta WHERE key = 'generation'").fetchone()
    gen = int(row[0]) if row else 0
    rows = {}
    for db, name, fmt, loc, typ, cols, parts, dv, hi in conn.execute(
        "SELECT namespace, table_name, format, location, table_type, columns_json, partition_cols, delta_version, "
        "hudi_instant "
        "FROM nb_tables WHERE catalog_name = 'spark_catalog'"
    ):
        rows[(db, name)] = {"fmt": fmt, "loc": loc, "type": typ, "cols": json.loads(cols),
                            "parts": json.loads(parts), "dv": dv, "hi": hi}
    namespaces = {r[0]: r[1] for r in conn.execute(
        "SELECT namespace, location FROM nb_namespaces WHERE catalog_name = 'spark_catalog'")}
    return gen, rows, namespaces


def iceberg_folder(meta):
    """Pasta de uma tabela Iceberg: pai de `metadata/` em `metadata_location` (sem validação estrita)."""
    parts = meta.rstrip("/").split("/")[:-1]
    return "/".join(parts[:-1] if parts and parts[-1] == "metadata" else parts)


def has_pending_table(conn):
    """A tabela `nb_pending_deletions` existe (o `catalog.db` já passou pela migração que a cria)."""
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'nb_pending_deletions'").fetchone() is not None


def enqueue_deletion(conn, catalog, key, location, stamp):
    """Põe na fila a pasta de uma tabela gerenciada dropada; idempotente por `location`. `False` sem a fila.

    Só enfileira: quem apaga os arquivos é o kernel, que rechecka o uso antes (`pending_deletions`).
    """
    if not has_pending_table(conn):
        return False
    conn.execute(
        "INSERT OR IGNORE INTO nb_pending_deletions (catalog, namespace, table_name, location, created_at) "
        "VALUES (?, ?, ?, ?, ?)", (catalog, key[0], key[1], location, stamp))
    return True


def folder_key(location):
    """Forma de comparar pastas: sem `/` final, em minúsculas (o MinIO não distingue caixa) e terminada em `/`."""
    return location.rstrip("/").lower() + "/"


def used_folders(conn, skip=None):
    """Pastas de tabela em uso (registro, Iceberg e glue), em `folder_key`; `skip`: chave `(schema, tabela)` do registro a ignorar."""
    used = [loc for ns, name, loc in conn.execute(
        "SELECT namespace, table_name, location FROM nb_tables WHERE catalog_name = 'spark_catalog'")
        if (ns, name) != skip]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'iceberg_tables'").fetchone():
        for (meta,) in conn.execute(
                "SELECT metadata_location FROM iceberg_tables WHERE catalog_name = 'iceberg' AND metadata_location IS NOT NULL"):
            used.append(iceberg_folder(meta))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'glue_tables'").fetchone():
        used += [loc for (loc,) in conn.execute("SELECT location FROM glue_tables WHERE location IS NOT NULL")]
    return [folder_key(u) for u in used if u]


def folder_in_use(conn, location, skip=None):
    """Alguma tabela (spark, iceberg ou glue; menos `skip`) usa a pasta: igual, dentro ou acima de `location`."""
    folder = folder_key(location)
    return any(u.startswith(folder) or folder.startswith(u) for u in used_folders(conn, skip))


def pending_rows(conn):
    """`[(id, namespace, tabela, location, reutilizada, attempts)]` da fila; só leitura."""
    used = used_folders(conn)
    rows = []
    for row_id, namespace, name, location, attempts in conn.execute(
            "SELECT id, namespace, table_name, location, attempts FROM nb_pending_deletions ORDER BY id").fetchall():
        folder = folder_key(location)
        reused = any(u.startswith(folder) or folder.startswith(u) for u in used)
        rows.append((row_id, namespace, name, location, reused, attempts))
    return rows


def pending_deletions(conn):
    """`[(id, (schema, tabela), location)]` das exclusões que o kernel pode executar agora; só leitura.

    Fica de fora a pasta em uso (igual, dentro ou acima da location de tabela do registro, do Iceberg ou do glue) e a
    linha que já esgotou `MAX_DELETE_ATTEMPTS`. A remoção das linhas de pasta reutilizada é `purge_reused_deletions`.
    """
    if not has_pending_table(conn):
        return []
    return [(row_id, (namespace, name), location)
            for row_id, namespace, name, location, reused, attempts in pending_rows(conn)
            if not reused and attempts < MAX_DELETE_ATTEMPTS]


def purge_reused_deletions(conn):
    """Tira da fila as linhas de pasta que uma tabela voltou a usar (nada é apagado). Escreve: só em POST/transação."""
    if not has_pending_table(conn):
        return
    for row_id, _namespace, _name, _location, reused, _attempts in pending_rows(conn):
        if reused:
            conn.execute("DELETE FROM nb_pending_deletions WHERE id = ?", (row_id,))


def finish_deletions(conn, done, failed):
    """Resultado da exclusão feita pelo kernel: `done` (ids) sai da fila; `failed` (`{id: texto}`) conta uma tentativa.

    Aproveita a transação para tirar da fila as linhas de pasta reutilizada (`purge_reused_deletions`).
    """
    for row_id in done:
        conn.execute("DELETE FROM nb_pending_deletions WHERE id = ?", (row_id,))
    for row_id, error in failed.items():
        conn.execute(
            "UPDATE nb_pending_deletions SET attempts = attempts + 1, last_error = ? WHERE id = ?",
            (str(error)[:200], row_id))
    purge_reused_deletions(conn)


def apply_plan(conn, plan, stamp, own_managed, type_from_row=False, destination=None, schema_location=None):
    """Aplica o plano do hook dentro da transação aberta pelo chamador; não toca em arquivos nem na generation.

    `plan`: `created` [(key, info)], `updated` [(key, rec_loc, rec_type, change)], `renamed` [(old, new, rec_loc, info)],
    `dropped` [(key, rec_loc)], `unregistered` [(key, rec_loc)] (só remove a linha), `new_dbs`, `gone_dbs`.
    `rec_loc` é a trava: só mexe na linha que ainda aponta para ele. `type_from_row`: tipo do update vem da linha (HTTP).
    `own_managed(key, loc)`: `loc` é a pasta gerenciada da tabela `key`; o tipo gravado deriva dela (MANAGED só aí,
    EXTERNAL em qualquer outra location s3) em `created`, `updated` e `renamed`, não do que o chamador informou.
    `destination` (`locations.table_destination`) liga a regra de destino (reservado, sobreposição, exclusão pendente)
    e o nome `<schema>.<t>` único entre os catálogos; recusas vão em `rejected` `(key, code)`, sem gravar.
    `schema_location(ns)` dá a location de um schema novo (sem ela, NULL). A MANAGED dropada sem outro uso entra na
    fila `nb_pending_deletions` e em `deletions`; `files_kept`: em uso ou fora da própria pasta gerenciada.
    """
    out = {"changed": False, "adopted": [], "conflicts": [], "updated_ok": [], "renamed_ok": [],
           "dropped_ok": [], "deletions": [], "files_kept": [], "rejected": []}
    changed = False
    has_iceberg = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'iceberg_tables'").fetchone()
    has_glue = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'glue_tables'").fetchone()
    pending_locs = []
    if destination is not None and has_pending_table(conn):
        pending_locs = [loc for (loc,) in conn.execute("SELECT location FROM nb_pending_deletions")]

    def bucket_of(loc):
        scheme, sep, rest = loc.partition("://")
        return rest.partition("/")[0] if sep and scheme.lower() in ("s3", "s3a", "s3n") else None

    # Lidas uma vez por chamada (a transação já segura o lock de escrita): `spark_locs` acompanha cada
    # INSERT/UPDATE/DELETE aprovado abaixo; `iceberg_locs` não muda aqui. Roda no kernel só com stdlib:
    # a pasta de uma tabela Iceberg é o pai de `metadata/`.
    spark_locs = {}
    iceberg_locs = []
    glue_locs = []
    if destination is not None:
        if has_glue:
            glue_locs = [loc for (loc,) in conn.execute("SELECT location FROM glue_tables WHERE location IS NOT NULL")]
        for ns, name, loc in conn.execute(
                "SELECT namespace, table_name, location FROM nb_tables WHERE catalog_name = 'spark_catalog'"):
            spark_locs[(ns, name)] = loc
        if has_iceberg:
            for (meta,) in conn.execute(
                    "SELECT metadata_location FROM iceberg_tables WHERE catalog_name = 'iceberg' AND metadata_location IS NOT NULL"):
                iceberg_locs.append(iceberg_folder(meta))

    # Remoções do plano saem da visão antes das criações: `DROP a` + `CREATE b` na mesma pasta é válido.
    for key, rec_loc in (*plan["dropped"], *plan.get("unregistered", ())):
        if spark_locs.get(key) == rec_loc:
            del spark_locs[key]

    def known_locations(skip_key):
        return [loc for key, loc in spark_locs.items() if key != skip_key] + iceberg_locs + glue_locs

    def name_in_iceberg(key):
        return bool(has_iceberg) and conn.execute(
            "SELECT 1 FROM iceberg_tables WHERE catalog_name = 'iceberg' AND lower(table_namespace) = lower(?) "
            "AND lower(table_name) = lower(?)", key).fetchone() is not None

    def name_in_glue(key):
        return bool(has_glue) and conn.execute(
            "SELECT 1 FROM glue_tables WHERE lower(database_name) = lower(?) AND lower(name) = lower(?)",
            key).fetchone() is not None

    def refusal(key, loc, skip_key, new_name):
        """Código da recusa (`InvalidLocation.code` ou nome repetido) ou `None`; sem `destination` a regra está desligada."""
        if destination is None:
            return None
        if new_name and (name_in_iceberg(key) or name_in_glue(key)):
            return "name_in_other_catalog"
        if bucket_of(loc) is None:
            return None
        try:
            destination(key[0], key[1], loc, known_locations(skip_key), None, pending_locs)
        except ValueError as exc:  # `InvalidLocation`
            return getattr(exc, "code", "invalid_location")
        return None

    def derived_type(key, loc, current, moved):
        """Tipo pela location s3; location local (legada) segue a regra antiga: MANAGED movida vira EXTERNAL."""
        if bucket_of(loc) is not None:
            return "MANAGED" if own_managed(key, loc) else "EXTERNAL"
        return "EXTERNAL" if current == "MANAGED" and moved else current

    def row_of(key):
        return conn.execute(
            "SELECT location, table_type FROM nb_tables WHERE catalog_name = 'spark_catalog' "
            "AND namespace = ? AND table_name = ?", key).fetchone()

    for key, info in plan["created"]:
        row = row_of(key)
        if row is None:
            code = refusal(key, info["loc"], None, True)
            if code:
                out["rejected"].append((key, code))
                continue
            conn.execute(
                "INSERT INTO nb_tables (catalog_name, namespace, table_name, format, location, table_type, "
                "columns_json, partition_cols, options_json, delta_version, hudi_instant, description, created_at, updated_at) "
                "VALUES ('spark_catalog', ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, ?, ?)",
                (*key, info["fmt"], info["loc"], derived_type(key, info["loc"], info["type"], False),
                 json.dumps(info["cols"]), json.dumps(info["parts"]),
                 info["dv"], info["hi"], info.get("description"), stamp, stamp))
            spark_locs[key] = info["loc"]
            changed = True
            out["adopted"].append(key)
        elif row[0] == info["loc"]:
            out["adopted"].append(key)
        else:
            out["conflicts"].append(key)
    for key, rec_loc, rec_type, change in plan["updated"]:
        typ = rec_type
        if type_from_row:
            row = row_of(key)
            typ = row[1] if row else rec_type
        typ = derived_type(key, change["loc"], typ, change["loc"] != rec_loc)
        code = refusal(key, change["loc"], key, False) if change["loc"] != rec_loc else None
        if code:
            out["rejected"].append((key, code))
            continue
        cur = conn.execute(
            "UPDATE nb_tables SET format = ?, location = ?, table_type = ?, columns_json = ?, partition_cols = ?, "
            "delta_version = ?, hudi_instant = ?, updated_at = ? WHERE catalog_name = 'spark_catalog' "
            "AND namespace = ? AND table_name = ? AND location = ?",
            (change["fmt"], change["loc"], typ, json.dumps(change["cols"]), json.dumps(change["parts"]),
             change["dv"], change["hi"], stamp, *key, rec_loc))
        if cur.rowcount:
            spark_locs[key] = change["loc"]
            changed = True
            out["updated_ok"].append((key, {**change, "type": typ}))
    for old, new, rec_loc, info in plan["renamed"]:
        old_row = row_of(old)
        code = refusal(new, info["loc"], old, True)
        if code:
            out["rejected"].append((new, code))
            continue
        typ = derived_type(new, info["loc"], old_row[1] if old_row is not None else None, info["loc"] != rec_loc)
        try:
            cur = conn.execute(
                "UPDATE nb_tables SET namespace = ?, table_name = ?, format = ?, location = ?, "
                "table_type = COALESCE(?, table_type), columns_json = ?, "
                "partition_cols = ?, delta_version = ?, hudi_instant = ?, updated_at = ? WHERE catalog_name = 'spark_catalog' "
                "AND namespace = ? AND table_name = ? AND location = ?",
                (*new, info["fmt"], info["loc"], typ, json.dumps(info["cols"]), json.dumps(info["parts"]), info["dv"],
                 info["hi"], stamp, *old, rec_loc))
        except sqlite3.IntegrityError:
            out["conflicts"].append(new)
            continue
        if cur.rowcount:
            spark_locs.pop(old, None)
            spark_locs[new] = info["loc"]
            changed = True
            out["renamed_ok"].append((old, new, info))
    for key, rec_loc in plan["dropped"]:
        row = row_of(key)
        out["dropped_ok"].append(key)
        if row is None or row[0] != rec_loc:
            continue  # outro kernel já removeu ou recriou
        conn.execute(
            "DELETE FROM nb_tables WHERE catalog_name = 'spark_catalog' AND namespace = ? AND table_name = ?", key)
        spark_locs.pop(key, None)
        changed = True
        if row[1] != "MANAGED":
            continue
        # Mesma comparação do drain (`folder_in_use`): registro, Iceberg e Glue, sem distinção de caixa.
        if folder_in_use(conn, row[0]) or not own_managed(key, row[0]):
            out["files_kept"].append(key)
        else:
            enqueue_deletion(conn, "spark_catalog", key, row[0], stamp)
            out["deletions"].append((key, row[0]))
    for key, rec_loc in plan.get("unregistered", ()):
        if key in out["dropped_ok"]:
            continue
        row = row_of(key)
        out["dropped_ok"].append(key)
        if row is None or row[0] != rec_loc:
            continue
        conn.execute(
            "DELETE FROM nb_tables WHERE catalog_name = 'spark_catalog' AND namespace = ? AND table_name = ?", key)
        spark_locs.pop(key, None)
        changed = True
    for ns in plan["new_dbs"]:
        try:
            ns_loc = schema_location(ns) if schema_location is not None else None
        except ValueError:  # nome que não cabe como pasta: o schema fica sem location gravada
            ns_loc = None
        changed |= conn.execute(
            "INSERT OR IGNORE INTO nb_namespaces (catalog_name, namespace, location, created_at) "
            "VALUES ('spark_catalog', ?, ?, ?)", (ns, ns_loc, stamp)).rowcount > 0
    for ns in plan["gone_dbs"]:
        left = conn.execute(
            "SELECT count(*) FROM nb_tables WHERE catalog_name = 'spark_catalog' AND namespace = ?", (ns,)).fetchone()[0]
        if not left:
            changed |= conn.execute(
                "DELETE FROM nb_namespaces WHERE catalog_name = 'spark_catalog' AND namespace = ?", (ns,)).rowcount > 0
    out["changed"] = changed
    return out


def _stored_schema_location(namespace: str) -> str:
    return locations.schema_location(namespace, "s3")


def read_generation(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM nb_meta WHERE key = 'generation'").fetchone()
    return int(row[0]) if row else 0


def commit_plan(conn: sqlite3.Connection, plan: dict[str, Any], own_managed: Any) -> dict[str, Any]:
    """Aplica o plano numa `BEGIN IMMEDIATE`, sobe a generation se algo mudou e devolve o resultado.

    O tipo dos updates vem da linha do registro; a regra de destino e a location dos schemas novos entram aqui (o
    hook local as passa a `apply_plan` por conta própria). `generation_before`/`generation` acompanham o resultado;
    as pastas MANAGED dropadas vão para a fila `nb_pending_deletions` na mesma transação e o kernel as apaga.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = read_generation(conn)
        result: dict[str, Any] = apply_plan(
            conn, plan, stamp, own_managed, type_from_row=True,
            destination=locations.table_destination, schema_location=_stored_schema_location)
        if result["changed"]:
            _bump_generation(conn)
        after = read_generation(conn)
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    result["generation_before"] = before
    result["generation"] = after
    return result
