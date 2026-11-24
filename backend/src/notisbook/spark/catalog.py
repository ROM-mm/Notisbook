"""Spark version catalog: newest 3.5 patch plus the newest patch of every 4.x line, with offline fallback.

The PyPI client is stdlib `urllib` run in a worker thread: one short GET per hour
does not justify a new runtime dependency, and the call stays off the event loop.
"""

import asyncio
import json
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

# Offline answer: one patch per offered line; a line missing here is only listed when PyPI answers.
FALLBACK_PATCH = {"3.5": "3.5.10", "4.0": "4.0.5", "4.1": "4.1.4", "4.2": "4.2.1", "4.3": "4.3.0"}

CACHE_TTL = 3600.0
FAILURE_RETRY = 60.0
FETCH_TIMEOUT = 5.0
MAX_BODY = 32 * 1024 * 1024
PYPI_PATH = "/pypi/pyspark/json"

# fullmatch + ASCII: `$` would accept a trailing newline and `\d` non-ASCII digits.
_VERSION = re.compile(r"\d+\.\d+\.\d+", re.ASCII)


def is_valid_version(version: str) -> bool:
    """The version is interpolated into a pip requirement and a path; keep it strictly numeric."""
    return _VERSION.fullmatch(version) is not None


@dataclass(frozen=True)
class CatalogEntry:
    version: str
    released_at: datetime | None
    line: str


@dataclass(frozen=True)
class Catalog:
    source: str  # "pypi" | "fallback"
    fallback: bool  # True when the list was not freshly resolved from PyPI
    entries: tuple[CatalogEntry, ...]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _line_of(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _is_offered_line(line: str) -> bool:
    """Only 3.5 and 4.0 onwards are offered; 3.5 is the oldest supported line."""
    key = _version_key(line)
    return key == (3, 5) or key >= (4, 0)


def _static_entries() -> tuple[CatalogEntry, ...]:
    return tuple(CatalogEntry(version, None, line) for line, version in FALLBACK_PATCH.items())


def _newest_first(entries: list[CatalogEntry]) -> tuple[CatalogEntry, ...]:
    return tuple(sorted(entries, key=lambda e: _version_key(e.version), reverse=True))


STATIC_CATALOG = Catalog("fallback", True, _newest_first(list(_static_entries())))


def _release_date(files: Any) -> datetime | None:
    """Earliest upload of the non-yanked files; None when the release has none usable."""
    if not isinstance(files, list):
        return None
    uploads: list[datetime] = []
    for item in files:
        if not isinstance(item, dict) or item.get("yanked"):
            continue
        try:
            moment = datetime.fromisoformat(str(item["upload_time_iso_8601"]))
        except (KeyError, ValueError):
            continue
        uploads.append(moment if moment.tzinfo else moment.replace(tzinfo=UTC))
    return min(uploads) if uploads else None


def parse_pypi(payload: Any) -> Catalog:
    """Highest stable non-yanked patch of line 3.5 and of every line from 4.0 on, bundle or not (newest first).

    A fallback line PyPI has no usable release for is added from `FALLBACK_PATCH` and marks the catalog as fallback.
    """
    releases = payload.get("releases") if isinstance(payload, dict) else None
    if not isinstance(releases, dict):
        raise TypeError("unexpected PyPI payload")
    best: dict[str, CatalogEntry] = {}
    for version, files in releases.items():
        if not isinstance(version, str) or not is_valid_version(version):
            continue
        line = _line_of(version)
        if not _is_offered_line(line) or (released := _release_date(files)) is None:
            continue
        current = best.get(line)
        if current is None or _version_key(version) > _version_key(current.version):
            best[line] = CatalogEntry(version, released, line)
    if not best:
        raise ValueError("no offered stable release in PyPI payload")
    missing = [e for e in _static_entries() if e.line not in best]
    return Catalog("pypi", bool(missing), _newest_first([*best.values(), *missing]))


def fetch_pypi(base_url: str, timeout: float = FETCH_TIMEOUT) -> Any:
    """Blocking GET of the pyspark JSON document; http(s) only, body size capped."""
    if urlsplit(base_url).scheme not in ("http", "https"):
        raise ValueError("NOTISBOOK_PYPI_URL must be http(s)")
    request = urllib.request.Request(
        base_url.rstrip("/") + PYPI_PATH, headers={"Accept": "application/json", "User-Agent": "notisbook"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise ValueError("PyPI response too large")
    return json.loads(body)


class CatalogService:
    """In-memory TTL cache; on failure serves the last good catalog, else the static list."""

    def __init__(
        self,
        base_url: str,
        *,
        ttl: float = CACHE_TTL,
        clock: Callable[[], float] = time.monotonic,
        fetch: Callable[[str], Any] = fetch_pypi,
    ) -> None:
        self._base_url = base_url
        self._ttl = ttl
        self._clock = clock
        self._fetch = fetch
        self._lock = asyncio.Lock()
        self._good: Catalog | None = None
        self._good_at = 0.0
        self._failed_at: float | None = None

    async def get(self) -> Catalog:
        async with self._lock:
            now = self._clock()
            if self._good is not None and now - self._good_at < self._ttl:
                return self._good
            if self._failed_at is not None and now - self._failed_at < FAILURE_RETRY:
                return self._degraded()
            try:
                payload = await asyncio.to_thread(self._fetch, self._base_url)
                catalog = parse_pypi(payload)
            except (OSError, ValueError, TypeError):
                self._failed_at = now
                return self._degraded()
            self._good, self._good_at, self._failed_at = catalog, now, None
            return catalog

    def _degraded(self) -> Catalog:
        if self._good is None:
            return STATIC_CATALOG
        return Catalog("fallback", True, self._good.entries)
