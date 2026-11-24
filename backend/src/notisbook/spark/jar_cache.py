"""Shared, content-addressed cache of S3A/bundle jars: `<home>/jars/<sha256>/<filename>`.

The SDK v2 jars weigh 558-686 MB, so each pinned jar is stored once and every env's `spark-defaults.conf`
points at it. The only source of truth for who uses a jar is the set of `spark-defaults.conf` files on disk
(no index that could diverge after a crash); installs in progress are protected by pins until they finish.
"""

import hashlib
import logging
import os
import re
import tempfile
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from .bundles import Artifact, maven_url

log = logging.getLogger(__name__)

JARS_DIR = "jars"
TMP_DIR = ".tmp"
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_CHUNK = 1 << 20
_SHA256_DIR = re.compile(r"[0-9a-f]{64}")
_CONF_GLOB = "envs/spark-*/spark-conf/spark-defaults.conf"


class JarError(Exception):
    """A jar could not be put in the cache; the message is user-facing."""


class JarCancelled(JarError):
    """The download was interrupted by the cancel event."""


class JarCache:
    def __init__(self, home: Path) -> None:
        self._root = Path(os.path.abspath(home)) / JARS_DIR
        self._home = self._root.parent
        # Guards `_inflight` and `_pins`; garbage collection holds it whole so a pin can never interleave with a sweep.
        self._lock = threading.Lock()
        self._inflight: dict[str, Future[Path]] = {}
        self._pins: dict[str, set[str]] = {}

    @property
    def root(self) -> Path:
        return self._root

    def path(self, artifact: Artifact) -> Path:
        """Where the jar lives (or will live) once `ensure` ran; never touches the disk."""
        return self._root / artifact.sha256 / artifact.filename

    def pin(self, job_id: str, artifacts: tuple[Artifact, ...] | list[Artifact]) -> None:
        """Protect the jars from `collect_garbage` until `unpin(job_id)`; call before `ensure`."""
        with self._lock:
            self._pins.setdefault(job_id, set()).update(a.sha256 for a in artifacts)

    def unpin(self, job_id: str) -> None:
        with self._lock:
            self._pins.pop(job_id, None)

    def ensure(self, artifact: Artifact, cancel: threading.Event) -> Path:
        """Blocking: leave a jar with the pinned sha256 in the cache and return its path.

        Concurrent calls for the same sha256 share one download. A jar already on disk is hashed again
        (a divergent file is deleted and downloaded anew). Raises JarError (JarCancelled when `cancel` fires),
        OSError or http.client.HTTPException.
        """
        while True:
            with self._lock:
                future = self._inflight.get(artifact.sha256)
                owner = future is None
                if future is None:
                    future = self._inflight[artifact.sha256] = Future()
            if owner:
                return self._run_owner(artifact, cancel, future)
            try:
                return self._wait(future, artifact, cancel)
            except JarCancelled:
                if cancel.is_set():
                    raise
                # The download we waited on was cancelled by another job: take it over.

    def _run_owner(self, artifact: Artifact, cancel: threading.Event, future: "Future[Path]") -> Path:
        try:
            path = self._materialize(artifact, cancel)
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(path)
            return path
        finally:
            with self._lock:
                self._inflight.pop(artifact.sha256, None)

    @staticmethod
    def _wait(future: "Future[Path]", artifact: Artifact, cancel: threading.Event) -> Path:
        while True:
            try:
                return future.result(timeout=1)
            except FutureTimeout:
                if cancel.is_set():
                    raise JarCancelled(f"download of {artifact.filename} cancelled") from None

    def _materialize(self, artifact: Artifact, cancel: threading.Event) -> Path:
        target = self.path(artifact)
        if target.is_file() and not target.is_symlink():
            if _sha256_of(target, cancel, artifact) == artifact.sha256:
                return target
            log.warning("cached jar %s does not match its pinned sha256; downloading it again", target)
        target.unlink(missing_ok=True)
        self._download(artifact, target, cancel)
        return target

    def _download(self, artifact: Artifact, target: Path, cancel: threading.Event) -> None:
        url = maven_url(artifact)
        if urlparse(url).scheme not in ("http", "https"):
            raise JarError(f"unsupported Maven URL scheme in {url}")
        tmp_dir = self._root / TMP_DIR
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=tmp_dir, prefix=f"{artifact.filename}.", suffix=".part")
        digest = hashlib.sha256()
        try:
            with urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response, os.fdopen(fd, "wb") as out:  # noqa: S310 (scheme checked above)
                while chunk := response.read(DOWNLOAD_CHUNK):
                    if cancel.is_set():
                        raise JarCancelled(f"download of {artifact.filename} cancelled")
                    digest.update(chunk)
                    out.write(chunk)
            if digest.hexdigest() != artifact.sha256:
                raise JarError(f"sha256 mismatch for {artifact.filename}: expected {artifact.sha256}, got {digest.hexdigest()}")
            if cancel.is_set():
                raise JarCancelled(f"download of {artifact.filename} cancelled")
            os.chmod(tmp, 0o444)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, target)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def collect_garbage(self) -> list[Path]:
        """Delete cached jars that no env's `spark-defaults.conf` references and no running job pinned.

        Any unreadable conf aborts the sweep without deleting anything (it could be the only reference).
        Also removes orphan partial downloads when no download is in progress. Returns the deleted files.
        """
        removed: list[Path] = []
        with self._lock:
            if not self._root.is_dir():
                return removed
            referenced = self._referenced()
            if referenced is None:
                return removed
            pinned = set().union(*self._pins.values()) if self._pins else set()
            for sha_dir in sorted(self._root.iterdir()):
                if not (_SHA256_DIR.fullmatch(sha_dir.name) and sha_dir.is_dir() and not sha_dir.is_symlink()):
                    continue
                if sha_dir.name in pinned:
                    continue
                for jar in sorted(sha_dir.iterdir()):
                    if jar not in referenced and _unlink(jar):
                        removed.append(jar)
                _rmdir_if_empty(sha_dir)
            if not self._inflight:
                removed += self._sweep_tmp()
        if removed:
            log.info("jar cache: removed %d unreferenced file(s)", len(removed))
        return removed

    def _referenced(self) -> set[Path] | None:
        """Jar paths under the cache named by any env conf; None when a conf cannot be read."""
        found: set[Path] = set()
        for conf in self._home.glob(_CONF_GLOB):
            try:
                text = conf.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                log.warning("jar cache: cannot read %s; skipping garbage collection", conf, exc_info=True)
                return None
            for line in text.splitlines():
                pair = line.split(None, 1)
                if len(pair) != 2:
                    continue
                key, value = pair[0], pair[1].strip()
                if key == "spark.jars":
                    entries = value.split(",")
                elif key == "spark.driver.extraClassPath":
                    entries = value.split(os.pathsep)
                else:
                    continue
                for entry in entries:
                    path = Path(os.path.abspath(entry))
                    if entry and path.is_relative_to(self._root):
                        found.add(path)
        return found

    def _sweep_tmp(self) -> list[Path]:
        tmp_dir = self._root / TMP_DIR
        if not tmp_dir.is_dir():
            return []
        return [leftover for leftover in sorted(tmp_dir.iterdir()) if _unlink(leftover)]


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        log.warning("jar cache: could not delete %s", path, exc_info=True)
        return False
    return True


def _rmdir_if_empty(directory: Path) -> None:
    """Drop `directory` when it is empty; a non-empty or busy folder is left alone."""
    try:
        directory.rmdir()
    except OSError:
        pass


def _sha256_of(path: Path, cancel: threading.Event, artifact: Artifact) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(DOWNLOAD_CHUNK):
            if cancel.is_set():
                raise JarCancelled(f"verification of {artifact.filename} cancelled")
            digest.update(chunk)
    return digest.hexdigest()
