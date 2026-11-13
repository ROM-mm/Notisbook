"""Directory listing by absolute path; reads metadata only, never file contents."""

import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .. import fs_safety
from ..catalog import iceberg_jdbc, registry
from ..catalog.store import catalog_db_path, connect
from ..config import default_root
from ..preferences import protected_paths


class BrowseError(Exception):
    status_code = 400


class InvalidPath(BrowseError):
    status_code = 400


class PathNotFound(BrowseError):
    status_code = 404


class PathForbidden(BrowseError):
    status_code = 403


class DeleteRefused(BrowseError):
    """Exclusão de pasta recusada; `detail` vai no corpo da resposta (`code` estável + `message`)."""

    def __init__(self, status_code: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail: dict[str, Any] = {"code": code, "message": message, **extra}


@dataclass(frozen=True)
class Place:
    label: str
    path: str


@dataclass(frozen=True)
class FileEntry:
    name: str
    path: str
    is_dir: bool
    is_symlink: bool
    size: int | None
    mtime: float | None


def places(notebooks_root: Path) -> list[Place]:
    return [Place("Home", str(Path.home())), Place("Notebooks", str(notebooks_root)), Place("Root", "/")]


def _is_dir(entry: os.DirEntry[str]) -> bool:
    try:
        # A link to a directory stays navigable; the link path itself is returned, never its target.
        return entry.is_dir()
    except OSError:
        return False


def _entry(entry: os.DirEntry[str], parent: str) -> FileEntry:
    is_symlink = entry.is_symlink()
    is_dir = _is_dir(entry)
    try:
        info = entry.stat(follow_symlinks=False)
        size: int | None = None if is_dir or is_symlink else info.st_size
        mtime: float | None = info.st_mtime
    except OSError:
        size, mtime = None, None
    return FileEntry(entry.name, os.path.join(parent, entry.name), is_dir, is_symlink, size, mtime)


def list_directory(path: str, offset: int, limit: int) -> dict[str, Any]:
    """List one directory level, directories first; no `resolve()` and no symlink traversal."""
    if not path or "\0" in path or not os.path.isabs(path):
        raise InvalidPath("path must be absolute")
    try:
        with os.scandir(path) as it:
            entries = [(not _is_dir(e), e.name.casefold(), e.name, e) for e in it]
    except FileNotFoundError as exc:
        raise PathNotFound("path not found") from exc
    except NotADirectoryError as exc:
        raise InvalidPath("path is not a directory") from exc
    except PermissionError as exc:
        raise PathForbidden("permission denied") from exc
    except OSError as exc:
        raise InvalidPath("path cannot be listed") from exc
    entries.sort(key=lambda e: e[:3])
    # `stat` runs only for the returned slice, not for every entry of a large directory.
    page = [_entry(e[3], path) for e in entries[offset : offset + limit]]
    end = offset + len(page)
    truncated = end < len(entries)
    return {
        "path": path,
        "parent": None if path == "/" else (os.path.dirname(path.rstrip("/")) or "/"),
        "entries": [asdict(e) for e in page],
        "total": len(entries),
        "truncated": truncated,
        "next_offset": end if truncated else None,
    }


@dataclass(frozen=True)
class DeleteTarget:
    lexical: Path
    real: Path
    is_link: bool


MAX_CITED_TABLES = 3
# Volumes externos montados: `/Volumes/<vol>/<algo>` é o mínimo aceito.
VOLUMES_ROOT = Path("/Volumes")


def _in_allowlist(real: Path, user_home: Path) -> bool:
    """Dentro da home do usuário ou de um volume montado; sem fold: caixa errada só recusa mais."""
    if real != user_home and fs_safety.is_within(real, user_home):
        return True
    return fs_safety.is_within(real, VOLUMES_ROOT) and len(real.parts) >= 4


def _refuse_protected(lexical: Path, real: Path, notebooks_root: Path, data_home: Path) -> None:
    """403 `protected_path` quando a pasta (já resolvida) não pode ser apagada pelo painel.

    Estritamente dentro de `<dados>/notebooks` (caixa exata) a pasta de dados, a allowlist e as pastas ocultas
    acima dessa raiz não valem; ela mesma, partes ocultas abaixo dela e a raiz ativa continuam protegidas.
    """
    data = data_home.resolve()
    managed = default_root(data)
    inside_managed = real != managed and fs_safety.is_within(real, managed)
    if inside_managed:
        below = real.relative_to(managed).parts
        # `lexical` fora de `managed` (alias por link): mantém todas as partes, o que só recusa mais.
        lexical_below = lexical.relative_to(managed).parts if fs_safety.is_within(lexical, managed) else lexical.parts
        hidden_parts = (*lexical_below, *below)
    else:
        hidden_parts = (*lexical.parts, *real.parts)
    reason: str | None = None
    if real == Path(real.anchor):
        reason = "The filesystem root cannot be deleted"
    elif fs_safety.is_protected(real, protected_paths(data_home), fold=True):
        reason = "This folder is protected or contains a protected folder"
    elif not inside_managed and fs_safety.is_within(real, data, fold=True):
        reason = "The Notisbook data folder cannot be deleted from here"
    elif any(part.startswith(".") for part in hidden_parts):
        reason = "Hidden folders cannot be deleted"
    elif not inside_managed and not _in_allowlist(real, Path.home().resolve()):
        reason = "Only folders in your home folder or on mounted volumes can be deleted"
    elif fs_safety.is_protected(real, (notebooks_root,), fold=True):
        reason = "The notebooks folder cannot be deleted from here"
    if reason is not None:
        raise DeleteRefused(403, "protected_path", reason)


def check_dir_delete(path: str, notebooks_root: Path, data_home: Path) -> DeleteTarget:
    """Valida o pedido e a política de proteção, sem apagar. I/O bloqueante: chame fora do event loop.

    Symlink: só o próprio link será removido, então a política olha o local do link (pai resolvido + nome).
    """
    if not path or "\0" in path or not os.path.isabs(path) or os.path.normpath(path) != path:
        raise DeleteRefused(400, "invalid_path", "path must be absolute and normalized")
    if not os.path.lexists(path):
        raise DeleteRefused(404, "path_not_found", "path not found")
    is_link = os.path.islink(path)
    dangling = is_link and not os.path.exists(path)  # link pendente: só o link é removido
    if not dangling and not os.path.isdir(path):
        raise DeleteRefused(400, "not_a_directory", "path is not a directory")
    lexical = Path(path)
    if is_link:
        real = Path(os.path.realpath(lexical.parent)) / lexical.name
    else:
        real = Path(os.path.realpath(lexical))
    _refuse_protected(lexical, real, notebooks_root, data_home)
    return DeleteTarget(lexical, real, is_link)


def _catalog_folders(conn: sqlite3.Connection) -> list[tuple[str, Path]]:
    """`(catalog.schema.tabela, pasta local)` de tabelas do registro `nb_*` e do Iceberg; remotas são ignoradas."""
    folders: list[tuple[str, Path]] = []
    for ns, name, location in conn.execute("SELECT namespace, table_name, location FROM nb_tables"):
        folder = registry.local_path(location)
        if folder is not None:
            folders.append((f"{registry.SPARK_CATALOG}.{ns}.{name}", folder))
    for ns, name, meta in conn.execute(
        "SELECT table_namespace, table_name, metadata_location FROM iceberg_tables WHERE metadata_location IS NOT NULL"
    ):
        folder = iceberg_jdbc.table_folder(meta)
        if folder is not None:
            folders.append((f"{iceberg_jdbc.ICEBERG_CATALOG}.{ns}.{name}", folder))
    return folders


def catalog_tables_overlapping(target: Path, data_home: Path) -> list[str]:
    """Tabelas registradas cuja pasta é igual, contém ou está dentro de `target` (comparação sem caixa).

    Levanta `DeleteRefused` 503 se o catálogo não puder ser lido: sem saber, não se apaga.
    """
    if not catalog_db_path(data_home).exists():
        return []
    try:
        conn = connect(data_home)
        try:
            conn.execute("PRAGMA query_only=ON")
            folders = _catalog_folders(conn)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise DeleteRefused(503, "catalog_unavailable", "The catalog could not be checked") from exc
    hits: list[str] = []
    for name, folder in folders:
        real = Path(os.path.realpath(folder))
        if fs_safety.is_within(real, target, fold=True) or fs_safety.is_within(target, real, fold=True):
            hits.append(name)
    return hits
