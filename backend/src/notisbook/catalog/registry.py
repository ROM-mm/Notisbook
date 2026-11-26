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
# Nó só de exibição: as tabelas Hudi vivem no `spark_catalog` (`nb_tables.format = 'hudi'`).
HUDI_CATALOG = "hudi"
DEFAULT_DATABASE = "default"
# Teto da varredura: tabelas por database e no total. Estourar o teto marca `"truncated": true`.
MAX_TABLES = 500
MAX_TOTAL_TABLES = 2000
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


def create_namespace(conn: sqlite3.Connection, namespace: str, display_catalog: str = SPARK_CATALOG) -> bool:
    """Registra o schema em minúsculas (como o SessionCatalog); `False` se já existe. Dentro de transação.

    `display_catalog` (`spark_catalog` ou `hudi`) é o nó onde o schema vazio aparece.
    """
    key = namespace.lower()
    if namespace_exists(conn, key):
        return False
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Sem `location`: o hook cria a pasta (`CREATE DATABASE IF NOT EXISTS`) ao hidratar a sessão.
    conn.execute(
        "INSERT INTO nb_namespaces (catalog_name, namespace, location, created_at, display_catalog) VALUES (?, ?, NULL, ?, ?)",
        (SPARK_CATALOG, key, stamp, display_catalog),
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


def namespace_hudi_count(conn: sqlite3.Connection, namespace: str) -> int:
    """Quantas tabelas do schema são Hudi (o nó `spark_catalog` não as lista, mas a exclusão do schema as remove)."""
    row = conn.execute(
        "SELECT COUNT(*) FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = ? AND format = 'hudi'",
        (SPARK_CATALOG, namespace.lower()),
    ).fetchone()
    return int(row[0])


def table_name_exists(conn: sqlite3.Connection, namespace: str, table: str) -> bool:
    """Existe `namespace.table` no registro `nb_tables`, sem distinção de caixa (colisão com o catálogo Iceberg)."""
    row = conn.execute(
        "SELECT 1 FROM nb_tables WHERE catalog_name = ? AND lower(namespace) = lower(?) AND lower(table_name) = lower(?)",
        (SPARK_CATALOG, namespace, table),
    ).fetchone()
    return row is not None


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


def _display_names(conn: sqlite3.Connection, hudi: bool) -> set[str]:
    """Schemas exibidos no nó: camadas sempre; `default` só com tabela do nó; demais por tabela ou origem vazia.

    As camadas (`locations.LAYERS`) aparecem sempre nos dois nós, mesmo vazias ou só com tabelas do outro formato.
    O `default` só aparece no nó em que tem tabela; vazio, é omitido nos dois.
    """
    counts: dict[str, tuple[int, int]] = {
        r[0]: (int(r[1]), int(r[2]))
        for r in conn.execute(
            "SELECT namespace, SUM(format = 'hudi'), SUM(format != 'hudi') FROM nb_tables WHERE catalog_name = ? GROUP BY namespace",
            (SPARK_CATALOG,),
        )
    }
    origins = {
        r[0]: r[1]
        for r in conn.execute("SELECT namespace, display_catalog FROM nb_namespaces WHERE catalog_name = ?", (SPARK_CATALOG,))
    }
    node = HUDI_CATALOG if hudi else SPARK_CATALOG
    names = set()
    for ns in {*locations.LAYERS, *counts, *origins}:
        n_hudi, n_other = counts.get(ns, (0, 0))
        empty_by_origin = n_hudi + n_other == 0 and ns != DEFAULT_DATABASE and origins.get(ns, SPARK_CATALOG) == node
        if ns in locations.LAYERS or (n_hudi if hudi else n_other) > 0 or empty_by_origin:
            names.add(ns)
    return names


def empty_display_names() -> list[str]:
    """Schemas dos nós spark e hudi sem `catalog.db`: só as camadas, na ordem de `locations.LAYERS`; sem `default`."""
    return list(locations.LAYERS)


def list_databases(conn: sqlite3.Connection, max_total: int, hudi: bool = False) -> tuple[list[dict[str, Any]], int]:
    """Databases do nó e o total de tabelas listadas: `spark_catalog` (sem as Hudi) ou, com `hudi`, só as Hudi.

    `max_total` é o que resta do teto global; databases após o teto voltam vazios e `truncated`.
    Cada schema é um só namespace do `spark_catalog`; a regra de exibição está em `_display_names`.
    """
    fmt_filter = "format = 'hudi'" if hudi else "format != 'hudi'"
    names = _display_names(conn, hudi)
    ordered = sorted(names, key=lambda n: (n != DEFAULT_DATABASE, locations.layer_rank(n), n))
    used = 0
    databases: list[dict[str, Any]] = []
    for db in ordered:
        if used >= max_total:
            databases.append({"name": db, "tables": [], "truncated": True})
            continue
        limit = min(MAX_TABLES, max_total - used)
        rows = conn.execute(
            "SELECT table_name, format, table_type, location, description FROM nb_tables "
            f"WHERE catalog_name = ? AND namespace = ? AND {fmt_filter} ORDER BY table_name LIMIT ?",
            (SPARK_CATALOG, db, limit + 1),
        ).fetchall()
        entry: dict[str, Any] = {"name": db, "tables": [_table_node(db, *r) for r in rows[:limit]]}
        if len(rows) > limit:
            entry["truncated"] = True
        used += len(entry["tables"])
        databases.append(entry)
    return databases, used


def catalog_summary(conn: sqlite3.Connection, hudi: bool = False) -> dict[str, Any]:
    """Contagens exatas do nó (sem `MAX_TABLES`/`MAX_TOTAL_TABLES`): por namespace e por formato.

    Os namespaces vêm de `_display_names`; `spark_catalog` conta o que não é Hudi e `hudi`, só o Hudi.
    O `spark_catalog` não tem views no registro.
    """
    fmt_filter = "format = 'hudi'" if hudi else "format != 'hudi'"
    per_namespace: dict[str, int] = {}
    formats: dict[str, int] = {}
    for namespace, fmt, count in conn.execute(
        f"SELECT namespace, format, COUNT(*) FROM nb_tables WHERE catalog_name = ? AND {fmt_filter} GROUP BY namespace, format",
        (SPARK_CATALOG,),
    ):
        per_namespace[namespace] = per_namespace.get(namespace, 0) + int(count)
        formats[fmt] = formats.get(fmt, 0) + int(count)
    names = _display_names(conn, hudi)
    ordered = sorted(names, key=lambda n: (n != DEFAULT_DATABASE, locations.layer_rank(n), n))
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


def read_table_info(conn: sqlite3.Connection, database: str, table: str, hudi_only: bool = False) -> dict[str, Any] | None:
    """Metadados de uma tabela Delta/Parquet/Hudi só do registro `nb_tables` (sem ler `_delta_log`/`.hoodie`).

    `hudi_only` serve ao nó de exibição `hudi`. `None` se a tabela não existir. Nomes sem distinção de caixa.
    """
    row = conn.execute(
        "SELECT namespace, table_name, format, location, table_type, columns_json, partition_cols, description, "
        "created_at, updated_at, delta_version, hudi_instant FROM nb_tables "
        "WHERE catalog_name = ? AND namespace = ? COLLATE NOCASE AND table_name = ? COLLATE NOCASE "
        "AND (? = 0 OR format = 'hudi')",
        (SPARK_CATALOG, database, table, int(hudi_only)),
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
        "catalog": HUDI_CATALOG if hudi_only else SPARK_CATALOG,
        "database": namespace,
        "table": name,
        "format": fmt,
        "table_type": table_type,
        # O DROP de uma MANAGED apaga a pasta s3a (`apply_plan` -> `deletions`) salvo se outra tabela a usa (`files_kept`).
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
    """`(generation, rows, namespaces)` do `spark_catalog`; `rows` por `(db, tabela)` com os campos que o hook usa."""
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
    namespaces = {r[0] for r in conn.execute("SELECT namespace FROM nb_namespaces WHERE catalog_name = 'spark_catalog'")}
    return gen, rows, namespaces


def iceberg_folder(meta):
    """Pasta de uma tabela Iceberg: pai de `metadata/` em `metadata_location` (sem validação estrita)."""
    parts = meta.rstrip("/").split("/")[:-1]
    return "/".join(parts[:-1] if parts and parts[-1] == "metadata" else parts)


def apply_plan(conn, plan, stamp, managed_shape, type_from_row=False, destination=None, protected_dbs=()):
    """Aplica o plano do hook dentro da transação aberta pelo chamador; não toca em arquivos nem na generation.

    `plan`: `created` [(key, info)], `updated` [(key, rec_loc, rec_type, change)], `renamed` [(old, new, rec_loc, info)],
    `dropped` [(key, rec_loc)], `unregistered` [(key, rec_loc)] (só remove a linha), `new_dbs`, `gone_dbs`.
    `rec_loc` é a trava: só mexe na linha que ainda aponta para ele. `type_from_row`: tipo do update vem da linha (HTTP).
    `destination` (`locations.table_destination`) liga a regra do notislake: camada pelo schema, sem sobrepor outra tabela
    (registro, Iceberg ou `glue`) e sem `<schema>.<t>` repetido no Iceberg ou no `glue`; recusas vão em `rejected`
    `(key, code)`, sem gravar.
    `protected_dbs` (camadas) nunca saem de `gone_dbs`. `deletions`/`files_kept`: MANAGED sem outro uso / ainda em uso.
    """
    out = {"changed": False, "adopted": [], "conflicts": [], "updated_ok": [], "renamed_ok": [],
           "dropped_ok": [], "deletions": [], "files_kept": [], "rejected": []}
    changed = False
    has_iceberg = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'iceberg_tables'").fetchone()
    has_glue = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'glue_tables'").fetchone()

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
        bucket = bucket_of(loc)
        if bucket is None:
            return None
        if bucket != "notislake":
            return "not_notislake"  # tabela do catálogo só no bucket notislake
        try:
            destination(key[0], key[1], loc, known_locations(skip_key))
        except ValueError as exc:  # `InvalidLocation`
            return getattr(exc, "code", "invalid_location")
        return None

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
                (*key, info["fmt"], info["loc"], info["type"], json.dumps(info["cols"]), json.dumps(info["parts"]),
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
        if typ == "MANAGED" and change["loc"] != rec_loc and not managed_shape(change["loc"]):
            typ = "EXTERNAL"
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
        typ = old_row[1] if old_row is not None else None
        if typ == "MANAGED" and info["loc"] != rec_loc and not managed_shape(info["loc"]):
            typ = "EXTERNAL"  # same rule as `updated`: MANAGED only in the MANAGED shape
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
        # Igual ou dentro da pasta, comparado por prefixo (sem LIKE, que trataria `%`/`_` como curinga).
        shared = conn.execute(
            "SELECT count(*) FROM nb_tables WHERE location = ?1 OR substr(location, 1, length(?1) + 1) = ?1 || '/'",
            (row[0].rstrip("/"),)).fetchone()[0]
        if not shared and has_iceberg:
            shared = conn.execute(
                "SELECT count(*) FROM iceberg_tables WHERE substr(metadata_location, 1, length(?1) + 1) = ?1 || '/'",
                (row[0].rstrip("/"),)).fetchone()[0]
        out["files_kept" if shared else "deletions"].append(key if shared else (key, row[0]))
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
        changed |= conn.execute(
            "INSERT OR IGNORE INTO nb_namespaces (catalog_name, namespace, location, created_at) "
            "VALUES ('spark_catalog', ?, NULL, ?)", (ns, stamp)).rowcount > 0
    for ns in plan["gone_dbs"]:
        if ns in protected_dbs:
            continue
        left = conn.execute(
            "SELECT count(*) FROM nb_tables WHERE catalog_name = 'spark_catalog' AND namespace = ?", (ns,)).fetchone()[0]
        if not left:
            changed |= conn.execute(
                "DELETE FROM nb_namespaces WHERE catalog_name = 'spark_catalog' AND namespace = ?", (ns,)).rowcount > 0
    out["changed"] = changed
    return out


def read_generation(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM nb_meta WHERE key = 'generation'").fetchone()
    return int(row[0]) if row else 0


def commit_plan(conn: sqlite3.Connection, plan: dict[str, Any], managed_shape: Any) -> dict[str, Any]:
    """Aplica o plano numa `BEGIN IMMEDIATE`, sobe a generation se algo mudou e devolve o resultado.

    O tipo dos updates vem da linha do registro; a regra de destino do notislake e as camadas protegidas entram
    aqui (o hook local as passa a `apply_plan` por conta própria). `generation_before`/`generation` acompanham
    o resultado; apagar pastas MANAGED (`deletions`) fica para o chamador, depois do COMMIT.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = read_generation(conn)
        result: dict[str, Any] = apply_plan(
            conn, plan, stamp, managed_shape, type_from_row=True,
            destination=locations.table_destination, protected_dbs=locations.LAYERS)
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
