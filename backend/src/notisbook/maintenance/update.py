"""`notisbook update [--version X.Y.Z]`: executa o `install.sh` da versão-alvo, já conferido.

Só vale para instalação via `uv tool`. A versão é validada por regex antes de qualquer rede e comparada
com a instalada (`packaging`): igual = nada a fazer; menor = recusado, pois o `catalog.db` não tem
proteção contra downgrade. O download usa `/usr/bin/curl` só com HTTPS; o `install.sh` é conferido
contra o `SHA256SUMS`, e a ausência da listagem é recusada (protege de corrupção, não de adulteração da mesma origem).
`NOTISBOOK_INSTALL_FROM=<dir>` lê os arquivos de uma pasta local. As mensagens saem em inglês.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.version import InvalidVersion, Version

from . import toolenv

REPO = "ROM-mm/Notisbook"
CURL = "/usr/bin/curl"
INSTALL_FROM_ENV = "NOTISBOOK_INSTALL_FROM"
VERSION_ENV = "NOTISBOOK_VERSION"
# Avisa o install.sh de que é update: só a primeira instalação instala os runtimes padrão.
UPDATING_ENV = "NOTISBOOK_UPDATING"
CURL_TIMEOUT_S = 120.0
SCRIPT_NAME = "install.sh"
SUMS_NAME = "SHA256SUMS"
# `$1` = script, `$2` = versão, `$3` = pasta temporária; nada do usuário entra na string do shell.
_SH_PROGRAM = 'sh "$1" --version "$2"; rc=$?; rm -rf "$3"; exit $rc'
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_TAG_URL = re.compile(r"/releases/tag/v([0-9][0-9.]*)$")
_WHEEL = re.compile(r"notisbook-([0-9][^-]*)-py3-none-any\.whl")


class UpdateError(Exception):
    """Falha esperada do update; a mensagem vai ao operador."""


def _curl(*args: str) -> str:
    try:
        result = subprocess.run(
            [CURL, "--proto", "=https", "--tlsv1.2", "-fsSL", *args],
            capture_output=True,
            text=True,
            timeout=CURL_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"could not run curl ({exc})") from None
    if result.returncode != 0:
        raise UpdateError(f"download failed (curl exit {result.returncode})")
    return result.stdout


def _download(url: str, dest: Path) -> None:
    _curl("--retry", "3", "-o", str(dest), url)


def latest_version() -> str:
    """Última release: segue o redirect de `/releases/latest`; cai para a API do GitHub."""
    try:
        effective = _curl("-I", "-o", "/dev/null", "-w", "%{url_effective}", f"https://github.com/{REPO}/releases/latest")
        match = _TAG_URL.search(effective.strip())
        if match and _VERSION.fullmatch(match.group(1)):
            return match.group(1)
    except UpdateError:
        pass
    try:
        tag = json.loads(_curl(f"https://api.github.com/repos/{REPO}/releases/latest")).get("tag_name", "")
    except (ValueError, AttributeError):
        tag = ""
    if not isinstance(tag, str) or not _VERSION.fullmatch(tag.removeprefix("v")):
        raise UpdateError("cannot determine the latest release; pass --version X.Y.Z")
    return tag.removeprefix("v")


def _local_version(source: Path) -> str:
    """Versão única listada no SHA256SUMS da pasta local, como faz o `install.sh`."""
    try:
        names = [line.split()[-1].lstrip("*") for line in (source / SUMS_NAME).read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        raise UpdateError(f"{SUMS_NAME} not found in {source}") from None
    versions = {m.group(1) for n in names if (m := _WHEEL.fullmatch(n))}
    if len(versions) != 1:
        raise UpdateError(f"{SUMS_NAME} in {source} must list exactly one Notisbook wheel; pass --version X.Y.Z")
    return versions.pop()


def _resolve_target(requested: str | None, source: Path | None) -> str:
    if requested is not None:
        return requested
    target = _local_version(source) if source is not None else latest_version()
    if not _VERSION.fullmatch(target):
        raise UpdateError(f"invalid release version {target!r}; pass --version X.Y.Z")
    return target


def _check_order(target: str, installed: str) -> int | None:
    """None = seguir com a atualização; senão o exit code (0 = já atualizado, 1 = recusado)."""
    try:
        wanted, current = Version(target), Version(installed)
    except InvalidVersion:
        raise UpdateError(f"cannot compare versions ({installed} -> {target})") from None
    if wanted == current:
        print(f"Notisbook {installed} is already up to date.")
        return 0
    if wanted < current:
        print(
            f"Notisbook: refusing to downgrade {installed} to {target}: the catalog database (catalog.db) may already "
            "use a newer schema that the older version cannot read.",
            file=sys.stderr,
        )
        return 1
    return None


def _listed_sha(sums: Path, name: str) -> str | None:
    try:
        text = sums.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise UpdateError(f"could not read {SUMS_NAME} ({exc.strerror or exc})") from None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def _verify_script(workdir: Path) -> None:
    script, sums = workdir / SCRIPT_NAME, workdir / SUMS_NAME
    expected = _listed_sha(sums, SCRIPT_NAME)
    if expected is None:
        raise UpdateError(f"{SCRIPT_NAME} is not listed in {SUMS_NAME}; refusing to run an unverified script")
    try:
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
    except OSError as exc:
        raise UpdateError(f"could not read {SCRIPT_NAME} ({exc.strerror or exc})") from None
    if digest != expected:
        raise UpdateError(f"{SCRIPT_NAME} does not match {SUMS_NAME}; the download is corrupt or was tampered with")


def _fetch_files(target: str, source: Path | None, workdir: Path) -> None:
    for name in (SCRIPT_NAME, SUMS_NAME):
        if source is None:
            _download(f"https://github.com/{REPO}/releases/download/v{target}/{name}", workdir / name)
            continue
        try:
            shutil.copyfile(source / name, workdir / name)
        except OSError:
            raise UpdateError(f"{name} not found in {source}") from None
    _verify_script(workdir)


def _source_dir() -> Path | None:
    raw = os.environ.get(INSTALL_FROM_ENV, "").strip()
    return Path(raw).expanduser() if raw else None


def run(target_version: str | None) -> int:
    """Executa o update; em sucesso o `execv` do shell substitui o processo e o exit code vem do `install.sh`."""
    requested = target_version.removeprefix("v") if target_version is not None else None
    if requested is not None and not _VERSION.fullmatch(requested):
        print(f"Notisbook: invalid version {target_version!r}; use the form X.Y.Z.", file=sys.stderr)
        return 2
    env = toolenv.detect()
    if not env.managed:
        print(
            "Notisbook: this is not a uv tool installation, so `update` is unavailable. "
            "Install with the official install.sh, or update your development checkout with git.",
            file=sys.stderr,
        )
        return 1
    source = _source_dir()
    workdir: Path | None = None
    try:
        target = _resolve_target(requested, source)
        done = _check_order(target, env.version)
        if done is not None:
            return done
        print(f"Updating Notisbook {env.version} -> {target}...", flush=True)
        try:
            workdir = Path(tempfile.mkdtemp(prefix="notisbook-update-"))
        except OSError as exc:
            raise UpdateError(f"could not create a temporary folder ({exc.strerror or exc})") from None
        _fetch_files(target, source, workdir)
    except UpdateError as exc:
        print(f"Notisbook: update failed: {exc}", file=sys.stderr)
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)
        return 1
    return _exec_installer(workdir, target)


def _exec_installer(workdir: Path, target: str) -> int:
    os.environ.pop(VERSION_ENV, None)
    os.environ[UPDATING_ENV] = "1"
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execv("/bin/sh", ["sh", "-c", _SH_PROGRAM, "sh", str(workdir / SCRIPT_NAME), target, str(workdir)])
    except OSError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        print(f"Notisbook: update failed: could not run the installer ({exc.strerror}).", file=sys.stderr)
        return 1
    return 0
