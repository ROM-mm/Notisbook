"""Execução do CLI `docker` (argv fixo, sem shell) e checagem de disponibilidade.

O contexto/endpoint do Docker é o do ambiente do operador (DOCKER_HOST, contexto ativo); este módulo
nunca o altera. O argv completo nunca é logado nem incluído em exceções, pois pode carregar caminhos
do operador; mensagens citam só o subcomando. A saída exibida ao usuário troca `$HOME` por `~`.
"""

import asyncio
import codecs
import logging
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

AVAILABILITY_TIMEOUT_S = 8.0
DEFAULT_TIMEOUT_S = 30.0
_CHUNK = 8192
_MAX_PENDING_LINE = 64 * 1024


class DockerError(RuntimeError):
    """Falha ao executar o CLI (ausente, timeout ou saída não nula quando exigida)."""


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def docker_binary() -> str | None:
    return shutil.which("docker")


def redact_home(text: str) -> str:
    """Troca o diretório home do operador (e sua forma resolvida) por `~`."""
    home = Path.home()
    for variant in sorted({str(home), str(home.resolve())}, key=len, reverse=True):
        text = text.replace(variant, "~")
    return text


def _binary() -> str:
    binary = docker_binary()
    if binary is None:
        raise DockerError("CLI docker não encontrado no PATH")
    return binary


def run(
    args: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    input_text: str | None = None,
) -> CliResult:
    """Executa `docker <args>` e devolve o resultado; só sobe DockerError para CLI ausente ou timeout."""
    verb = args[0] if args else ""
    try:
        completed = subprocess.run(
            [_binary(), *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            stdin=None if input_text is not None else subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerError(f"docker {verb}: tempo esgotado após {timeout:g}s") from exc
    except OSError as exc:
        raise DockerError(
            f"docker {verb}: não foi possível executar ({type(exc).__name__})"
        ) from exc
    return CliResult(completed.returncode, completed.stdout, completed.stderr)


def is_available(timeout: float = AVAILABILITY_TIMEOUT_S) -> bool:
    """True se o daemon responde; qualquer falha (CLI ausente, Colima parado, timeout) devolve False."""
    try:
        return (
            run(["info", "--format", "{{.ServerVersion}}"], timeout=timeout).returncode
            == 0
        )
    except DockerError as exc:
        logger.info("Docker indisponível: %s", exc)
        return False


async def stream(
    args: Sequence[str],
    emit: Callable[[str], Awaitable[None]],
    *,
    timeout: float,
) -> int:
    """Executa `docker <args>` enviando cada linha (stdout+stderr, com `$HOME`→`~`) a `emit`; devolve o código de saída."""
    verb = args[0] if args else ""
    try:
        process = await asyncio.create_subprocess_exec(
            _binary(),
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        raise DockerError(
            f"docker {verb}: não foi possível executar ({type(exc).__name__})"
        ) from exc
    assert process.stdout is not None
    try:
        async with asyncio.timeout(timeout):
            await _pump(process.stdout, emit)
            return await process.wait()
    except TimeoutError as exc:
        raise DockerError(f"docker {verb}: tempo esgotado após {timeout:g}s") from exc
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _pump(
    reader: asyncio.StreamReader, emit: Callable[[str], Awaitable[None]]
) -> None:
    """Divide a saída em linhas por `\\n` ou `\\r` (progresso do build) e as entrega redigidas."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    while chunk := await reader.read(_CHUNK):
        pending += decoder.decode(chunk)
        parts = pending.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        pending = parts.pop()
        if len(pending) > _MAX_PENDING_LINE:
            parts.append(pending)
            pending = ""
        for line in parts:
            if line.strip():
                await emit(redact_home(line.rstrip()))
    if pending.strip():
        await emit(redact_home(pending.rstrip()))
