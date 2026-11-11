"""Helpers shared by the exporters: cell language, normalized source and download names."""

import re
from typing import Any, Literal

from ..notebooks.store import validate_notebook

__all__ = ["CellLanguage", "cell_language", "cell_source", "download_name", "validate_notebook"]

CellLanguage = Literal["python", "sql", "duckdb"]

_MAX_NAME = 120
_UNSAFE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f"\\/;]')


def cell_language(cell: dict[str, Any]) -> CellLanguage:
    """Language of a code cell from `metadata.notisbook.language`; absent or unknown means Python."""
    meta = cell.get("metadata")
    notisbook = meta.get("notisbook") if isinstance(meta, dict) else None
    language = notisbook.get("language") if isinstance(notisbook, dict) else None
    if language == "sql":
        return "sql"
    if language == "duckdb":
        return "duckdb"
    return "python"


def cell_source(cell: dict[str, Any]) -> str:
    """Cell source as one string with `\\n` line endings (nbformat allows str or list of str)."""
    source = cell.get("source", "")
    text = "".join(source) if isinstance(source, list) else str(source)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def download_name(notebook_name: str, extension: str) -> str:
    """Safe download file name: last path segment of `notebook_name` with its extension swapped.

    Never used to touch the disk; only feeds `Content-Disposition`.
    """
    last = re.split(r"[/\\]", notebook_name)[-1]
    stem = last.rsplit(".", 1)[0] if "." in last.strip(".") else last
    stem = _UNSAFE_NAME_CHARS.sub("", stem).strip(" .")
    stem = stem[: _MAX_NAME - len(extension) - 1].strip(" .")
    return f"{stem}.{extension}" if stem else f"notebook.{extension}"
