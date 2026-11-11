"""Sandboxed notebook storage under a single root directory.

Every public method takes a root-relative POSIX path and raises a `StoreError`
subclass carrying the HTTP status the API layer should answer with.
"""

import os
import posixpath
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import nbformat
from nbformat.v4 import new_notebook

from .. import fs_safety

NOTEBOOK_SUFFIX = ".ipynb"
# Cell ids (and therefore schema 4.5) are required for notebooks we write.
MIN_MINOR = 5


class StoreError(Exception):
    status_code = 400


class InvalidPath(StoreError):
    status_code = 400


class OutsideRoot(StoreError):
    status_code = 403


class NotFound(StoreError):
    status_code = 404


class Conflict(StoreError):
    status_code = 409


class InvalidNotebook(StoreError):
    status_code = 422


class PartialDelete(StoreError):
    status_code = 500


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    type: str  # "dir" | "notebook" | "file"
    mtime: float
    size: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ensure_cell_ids(nb: Any) -> None:
    for cell in nb.get("cells", []):
        if isinstance(cell, dict) and not cell.get("id"):
            cell["id"] = uuid.uuid4().hex[:8]


def _normalize(raw: Any) -> Any:
    """Coerce to a valid nbformat v4.5 node or raise InvalidNotebook."""
    if not isinstance(raw, dict) or raw.get("nbformat") != 4:
        raise InvalidNotebook("Not an nbformat v4 notebook")
    nb = nbformat.from_dict(raw)
    if nb.get("nbformat_minor", 0) < MIN_MINOR:
        nb["nbformat_minor"] = MIN_MINOR
    cells = nb.get("cells")
    if not isinstance(cells, list):
        raise InvalidNotebook("Notebook 'cells' must be a list")
    _ensure_cell_ids(nb)
    try:
        nbformat.validate(nb)
    except nbformat.ValidationError as exc:
        raise InvalidNotebook(f"Invalid notebook: {exc.message}") from exc
    return nb


def validate_notebook(raw: Any) -> Any:
    """Return `raw` as a validated nbformat v4.5 node or raise InvalidNotebook (no disk access)."""
    return _normalize(raw)


class NotebookStore:
    def __init__(self, root: Path, protected: tuple[Path, ...] = ()) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()
        # Caminhos resolvidos que `delete` nunca remove (nem seus ancestrais), mesmo com `--root` da CLI.
        self._protected = tuple(p.resolve() for p in protected)

    def _clean(self, rel: str) -> str:
        if "\x00" in rel:
            raise InvalidPath("NUL byte in path")
        if rel.startswith(("/", "\\")) or posixpath.isabs(rel) or (len(rel) > 1 and rel[1] == ":"):
            raise InvalidPath("Absolute paths are not allowed")
        norm = posixpath.normpath(rel) if rel else "."
        if norm == ".." or norm.startswith("../"):
            raise InvalidPath("Path escapes the root")
        return norm

    def resolve(self, rel: str) -> Path:
        """Resolve inside the root; symlinks pointing outside yield 403."""
        target = (self.root / self._clean(rel)).resolve()
        if not target.is_relative_to(self.root):
            raise OutsideRoot("Path resolves outside the root")
        return target

    def _relpath(self, target: Path) -> str:
        return target.relative_to(self.root).as_posix() if target != self.root else ""

    def _entry(self, target: Path) -> Entry:
        st = target.stat()
        if target.is_dir():
            kind, size = "dir", None
        else:
            kind = "notebook" if target.suffix == NOTEBOOK_SUFFIX else "file"
            size = st.st_size
        return Entry(target.name, self._relpath(target), kind, st.st_mtime, size)

    @staticmethod
    def _require_notebook_name(target: Path) -> None:
        if target.suffix != NOTEBOOK_SUFFIX:
            raise InvalidPath("Only .ipynb files can be written")

    def stat(self, rel: str) -> Entry:
        target = self.resolve(rel)
        if not target.exists():
            raise NotFound(rel)
        return self._entry(target)

    def list_dir(self, rel: str = "") -> list[Entry]:
        target = self.resolve(rel)
        if not target.exists():
            raise NotFound(rel)
        if not target.is_dir():
            raise InvalidPath("Not a directory")
        entries: list[Entry] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            try:
                resolved = child.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if not resolved.is_relative_to(self.root):
                continue
            entries.append(self._entry(child))
        return entries

    def read_notebook(self, rel: str) -> Any:
        target = self.resolve(rel)
        if not target.exists():
            raise NotFound(rel)
        if not target.is_file():
            raise InvalidPath("Not a file")
        self._require_notebook_name(target)
        try:
            nb = nbformat.read(target, as_version=4)
        except Exception as exc:  # nbformat raises assorted parse/schema errors
            raise InvalidNotebook(f"Cannot read notebook: {exc}") from exc
        if nb.get("nbformat_minor", 0) < MIN_MINOR:
            nb["nbformat_minor"] = MIN_MINOR
        _ensure_cell_ids(nb)
        return nb

    def write_notebook(self, rel: str, raw: Any) -> Entry:
        target = self.resolve(rel)
        self._require_notebook_name(target)
        if target.is_dir():
            raise InvalidPath("Path is a directory")
        if not target.parent.is_dir():
            raise NotFound("Parent directory does not exist")
        nb = _normalize(raw)
        self._atomic_write(target, nbformat.writes(nb, version=4))
        return self._entry(target)

    def create(self, rel: str, kind: str = "notebook") -> Entry:
        target = self.resolve(rel)
        if target == self.root or target.exists():
            raise Conflict("Already exists")
        if kind == "directory":
            target.mkdir(parents=True)
            return self._entry(target)
        self._require_notebook_name(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, nbformat.writes(_normalize(new_notebook()), version=4))
        return self._entry(target)

    def rename(self, rel: str, new_rel: str) -> Entry:
        source = self.resolve(rel)
        dest = self.resolve(new_rel)
        if source == self.root:
            raise InvalidPath("Cannot rename the root")
        if not source.exists():
            raise NotFound(rel)
        if source.is_file():
            self._require_notebook_name(source)
            self._require_notebook_name(dest)
        if dest.exists():
            raise Conflict("Destination already exists")
        if not dest.parent.is_dir():
            raise NotFound("Destination directory does not exist")
        if source.is_dir() and dest.is_relative_to(source):
            raise InvalidPath("Cannot move a directory into itself")
        # Not race-free: os.rename overwrites silently if dest appears after the check.
        os.rename(source, dest)
        return self._entry(dest)

    def blocking_paths(self, rel: str) -> list[Path]:
        """Alvos absolutos resolvidos que uma sessão aberta impede de renomear/excluir.

        Inclui o caminho (pai resolvido + nome) e, se for symlink, o destino real.
        """
        norm = self._clean(rel)
        if norm == ".":
            return []
        lexical = self.resolve(posixpath.dirname(norm)) / posixpath.basename(norm)
        resolved = lexical.resolve()
        return [lexical] if resolved == lexical else [lexical, resolved]

    def delete(self, rel: str) -> None:
        """Remove um .ipynb ou uma pasta (recursivo); symlink remove só o link."""
        norm = self._clean(rel)
        if norm == ".":
            raise InvalidPath("Cannot delete the root")
        if any(part.startswith(".") for part in norm.split("/")):
            raise InvalidPath("Hidden paths cannot be deleted")
        parent = self.resolve(posixpath.dirname(norm))
        target = parent / posixpath.basename(norm)
        if not os.path.lexists(target):
            raise NotFound(rel)
        if target.is_symlink():
            self._unlink(target)
        elif target.is_dir():
            real = target.resolve()
            if fs_safety.is_protected(real, self._protected):
                raise InvalidPath("This folder contains a protected folder and cannot be deleted")
            try:
                fs_safety.remove_tree(target)
            except fs_safety.PartialDelete as exc:
                raise PartialDelete(str(exc)) from exc
        else:
            self._require_notebook_name(target)
            self._unlink(target)

    @staticmethod
    def _unlink(target: Path) -> None:
        """Remove um arquivo/link; a falha não deixa nada pela metade, então não é `PartialDelete`."""
        try:
            target.unlink()
        except OSError as exc:
            raise Conflict(f"Could not delete: {exc.strerror or 'operation failed'}") from exc

    @staticmethod
    def _atomic_write(target: Path, text: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".nb-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            if target.exists():
                os.chmod(tmp_name, target.stat().st_mode & 0o777)
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
