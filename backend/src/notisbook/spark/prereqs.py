"""Host prerequisites for Spark environments: uv and the JDK each Spark line needs."""

import asyncio
import os
import re
import shutil
from asyncio.subprocess import DEVNULL, PIPE, STDOUT
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_JAVA = 17
JAVA_HOME_TOOL = Path("/usr/libexec/java_home")
# Test seam: path of an executable that replaces java_home (e.g. one that finds no JDK).
JAVA_HOME_TOOL_ENV = "NOTISBOOK_JAVA_HOME_TOOL"
PROBE_TIMEOUT = 15.0
_JAVA_VERSION = re.compile(r'version "([^"]+)"')
_MAJOR = re.compile(r"(\d+)(?:\.(\d+))?")
# `    17.0.21 (arm64) "Vendor" - "OpenJDK 17.0.21" /path/to/Home`
_JDK_LINE = re.compile(r'^\s+(\S+)\s+\([^)]*\)\s.*"\s(/.*)$')


@dataclass(frozen=True)
class Prereqs:
    uv_found: bool
    uv_version: str | None
    java_version: str | None
    java_ok: bool
    java_home: str | None
    jdks: tuple[tuple[str, str], ...] = ()
    spark3_ok: bool = False
    spark4_ok: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "uv": {"found": self.uv_found, "version": self.uv_version},
            "java": {
                "version": self.java_version,
                "ok": self.java_ok,
                "jdks": [{"version": v, "home": h} for v, h in self.jdks],
                "spark3_ok": self.spark3_ok,
                "spark4_ok": self.spark4_ok,
            },
            "java_home": self.java_home,
        }


async def _capture(args: list[str], *, merge_stderr: bool) -> tuple[int, str] | None:
    """Run a short probe; None when it cannot start or exceeds the timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT if merge_stderr else DEVNULL
        )
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), PROBE_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return None
    return proc.returncode or 0, out.decode(errors="replace")


def java_major(version: str) -> int | None:
    """`17.0.2` -> 17, `1.8.0_292` -> 8, `21-ea` -> 21."""
    match = _MAJOR.match(version)
    if match is None:
        return None
    if match.group(1) == "1" and match.group(2):
        return int(match.group(2))
    return int(match.group(1))


async def resolve_java_home() -> str | None:
    """`$JAVA_HOME` wins; otherwise ask macOS for a JDK 17+."""
    configured = os.environ.get("JAVA_HOME")
    if configured:
        return configured
    tool = _java_home_tool()
    if _tool_usable(tool):
        result = await _capture([str(tool), "-v", f"{MIN_JAVA}+"], merge_stderr=False)
        if result is not None and result[0] == 0 and result[1].strip():
            return result[1].strip()
    return None


def _java_home_tool() -> Path:
    override = os.environ.get(JAVA_HOME_TOOL_ENV)
    return Path(override) if override else JAVA_HOME_TOOL


def _tool_usable(tool: Path) -> bool:
    return tool.is_file() and os.access(tool, os.X_OK)


async def list_jdks() -> list[tuple[str, str]]:
    """JDKs known to `java_home -V` as `(version, home)`; the listing goes to stderr."""
    tool = _java_home_tool()
    if not _tool_usable(tool):
        return []
    try:
        proc = await asyncio.create_subprocess_exec(str(tool), "-V", stdin=DEVNULL, stdout=DEVNULL, stderr=PIPE)
        _, err = await asyncio.wait_for(proc.communicate(), PROBE_TIMEOUT)
    except OSError:
        return []
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return []
    matches = (_JDK_LINE.match(line) for line in err.decode(errors="replace").splitlines())
    return [(m.group(1), m.group(2)) for m in matches if m is not None]


async def jdk_home(major: int) -> str | None:
    """Home of the JDK `java_home -v <major>` picks (exact major), or None."""
    tool = _java_home_tool()
    if not _tool_usable(tool):
        return None
    result = await _capture([str(tool), "-v", str(major)], merge_stderr=False)
    if result is None or result[0] != 0:
        return None
    home = result[1].strip()
    return home if home and os.access(Path(home) / "bin" / "java", os.X_OK) else None


def spark_major(version: str) -> int | None:
    match = re.match(r"(\d+)", version)
    return int(match.group(1)) if match else None


def jdk_candidates(version: str) -> tuple[int, ...]:
    """JDK majors by preference: Spark 3.x -> 17; any other line follows the 4.x rule, 21 then 17."""
    return (17,) if spark_major(version) == 3 else (21, 17)


async def _home_major(home: str) -> int | None:
    """Major of the JDK at `home`, from its `release` file, else `bin/java -version`; None if unusable."""
    java = Path(home) / "bin" / "java"
    if not os.access(java, os.X_OK):
        return None
    try:
        text = (Path(home) / "release").read_text(errors="replace")
    except OSError:
        text = ""
    match = re.search(r'^JAVA_VERSION="([^"]+)"', text, re.MULTILINE)
    if match is None:
        result = await _capture([str(java), "-version"], merge_stderr=True)
        match = _JAVA_VERSION.search(result[1]) if result is not None else None
    return java_major(match.group(1)) if match else None


async def _brew_prefix() -> Path | None:
    brew = shutil.which("brew")
    if brew is None:
        return None
    result = await _capture([brew, "--prefix"], merge_stderr=False)
    if result is None or result[0] != 0 or not result[1].strip():
        return None
    return Path(result[1].strip())


async def brew_jdk_home(major: int) -> str | None:
    """Home of Homebrew's keg-only `openjdk@<major>`, which `java_home` cannot see; None if absent."""
    prefix = await _brew_prefix()
    if prefix is None:
        return None
    home = prefix / "opt" / f"openjdk@{major}" / "libexec" / "openjdk.jdk" / "Contents" / "Home"
    return str(home) if os.access(home / "bin" / "java", os.X_OK) else None


async def jdk_for_spark(version: str) -> str | None:
    """JAVA_HOME for a Spark version, or None when no compatible JDK is installed.

    Order: `$JAVA_HOME` if it points to an accepted major, then per major `java_home -v`, then the Homebrew keg.
    """
    candidates = jdk_candidates(version)
    configured = os.environ.get("JAVA_HOME")
    if configured and await _home_major(configured) in candidates:
        return configured
    for major in candidates:
        home = await jdk_home(major) or await brew_jdk_home(major)
        if home is not None:
            return home
    return None


async def _uv_version(uv: str) -> str | None:
    result = await _capture([uv, "--version"], merge_stderr=True)
    if result is None or result[0] != 0:
        return None
    parts = result[1].split()
    return parts[1] if len(parts) > 1 else None


async def _java_version(java_home: str | None) -> str | None:
    """Version of the JVM Spark will actually use: `$JAVA_HOME/bin/java`, else the one on PATH."""
    candidate = Path(java_home) / "bin" / "java" if java_home else None
    java = str(candidate) if candidate and os.access(candidate, os.X_OK) else shutil.which("java")
    if java is None:
        return None
    result = await _capture([java, "-version"], merge_stderr=True)
    if result is None or result[0] != 0:
        return None
    match = _JAVA_VERSION.search(result[1])
    return match.group(1) if match else None


async def check_prereqs() -> Prereqs:
    uv = shutil.which("uv")
    uv_version = await _uv_version(uv) if uv else None
    java_home = await resolve_java_home()
    java_version = await _java_version(java_home)
    jdks = await list_jdks()
    major = java_major(java_version) if java_version else None
    return Prereqs(
        uv_found=uv is not None,
        uv_version=uv_version,
        java_version=java_version,
        java_ok=major is not None and major >= MIN_JAVA,
        java_home=java_home,
        jdks=tuple(jdks),
        spark3_ok=await jdk_for_spark("3") is not None,
        spark4_ok=await jdk_for_spark("4") is not None,
    )
