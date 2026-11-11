"""Spark version catalog: stable pyspark releases from PyPI, with offline fallback.

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
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

SUGGESTED_VERSIONS = ("3.5.9", "4.3.0")

WINDOW = timedelta(days=180)
FALLBACK_COUNT = 3
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


@dataclass(frozen=True)
class Catalog:
    source: str  # "pypi" | "fallback"
    fallback: bool  # True when the list is not the strict 180-day window
    entries: tuple[CatalogEntry, ...]


STATIC_CATALOG = Catalog("fallback", True, tuple(CatalogEntry(v, None) for v in SUGGESTED_VERSIONS))


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


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


def parse_pypi(payload: Any, now: datetime) -> Catalog:
    """Stable releases only, newest first; the last 180 days or the 3 latest when that is empty."""
    releases = payload.get("releases") if isinstance(payload, dict) else None
    if not isinstance(releases, dict):
        raise TypeError("unexpected PyPI payload")
    stable = [
        CatalogEntry(version, released)
        for version, files in releases.items()
        if isinstance(version, str) and is_valid_version(version) and (released := _release_date(files))
    ]
    if not stable:
        raise ValueError("no stable release in PyPI payload")
    stable.sort(key=lambda e: (e.released_at, _version_key(e.version)), reverse=True)
    cutoff = now - WINDOW
    recent = [e for e in stable if e.released_at is not None and e.released_at >= cutoff]
    if recent:
        return Catalog("pypi", False, tuple(recent))
    return Catalog("pypi", True, tuple(stable[:FALLBACK_COUNT]))


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
                catalog = parse_pypi(payload, datetime.now(UTC))
            except (OSError, ValueError, TypeError):
                self._failed_at = now
                return self._degraded()
            self._good, self._good_at, self._failed_at = catalog, now, None
            return catalog

    def _degraded(self) -> Catalog:
        if self._good is None:
            return STATIC_CATALOG
        return Catalog("fallback", True, self._good.entries)
