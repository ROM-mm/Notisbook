"""Libs de um ambiente Spark instalado: listagem e comandos `uv pip` restritos ao PyPI.

Só argv (nunca shell). A origem é fixada aqui: `--no-config`, `--default-index` vindo da
configuração do Notisbook e ambiente sem `UV_*` fora da allowlist; a entrada do usuário
só chega como nome/spec já validados por `requirements.py`.
"""

import asyncio
import contextlib
import json
from asyncio.subprocess import DEVNULL, PIPE
from collections.abc import Mapping, Sequence
from pathlib import Path

from packaging.utils import canonicalize_name

LIST_TIMEOUT = 60
# Configurações de `uv` que o operador pode manter; qualquer outra `UV_*` poderia trocar a origem.
UV_ALLOWLIST = ("UV_CACHE_DIR", "UV_LINK_MODE", "UV_NATIVE_TLS", "UV_HTTP_TIMEOUT")


class PackagesError(Exception):
    """Falha ao listar as libs; a mensagem é segura para o usuário."""


class UvNotFound(Exception):
    """O executável `uv` não está no PATH."""


def package_env(base: Mapping[str, str]) -> dict[str, str]:
    """Cópia de `base` sem as variáveis `UV_*` fora da allowlist e com `UV_LINK_MODE=copy`."""
    env = {k: v for k, v in base.items() if not k.startswith("UV_") or k in UV_ALLOWLIST}
    env["UV_LINK_MODE"] = "copy"
    return env


def index_url(pypi_url: str) -> str:
    return f"{pypi_url.rstrip('/')}/simple"


def list_args(uv: str, python: str) -> list[str]:
    return [uv, "pip", "list", "--python", python, "--format", "json", "--no-config"]


def core_pins(installed: Sequence[Mapping[str, str]], core: set[str]) -> list[str]:
    """Pins `nome==versão` das libs base instaladas, para a resolução nunca movê-las."""
    return [
        f"{canonicalize_name(item['name'])}=={item['version']}"
        for item in installed
        if canonicalize_name(item["name"]) in core
    ]


def install_args(
    uv: str,
    python: str,
    pypi_url: str,
    upgrade: Sequence[str],
    requirements: Sequence[str],
    pins: Sequence[str] = (),
) -> list[str]:
    """`-P <nome>` leva cada lib à maior versão permitida pela spec (e atualiza a já instalada).

    `pins` entram como requisitos extras: um conflito com as libs base faz o uv falhar.
    """
    args = [uv, "pip", "install", "--python", python, "--no-config", "--default-index", index_url(pypi_url)]
    for name in upgrade:
        args += ["-P", name]
    return [*args, *requirements, *pins]


def uninstall_args(uv: str, python: str, names: Sequence[str]) -> list[str]:
    return [uv, "pip", "uninstall", "--python", python, "--no-config", *names]


async def list_installed(uv: str, env_dir: Path, env: Mapping[str, str]) -> list[dict[str, str]]:
    """Libs do ambiente como `{name, version}`, ordenadas por nome canônico."""
    args = list_args(uv, str(env_dir / "bin" / "python"))
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, env=dict(env)
        )
    except OSError as exc:
        raise PackagesError(f"cannot start uv: {exc.strerror}") from exc
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), LIST_TIMEOUT)
    except TimeoutError as exc:
        raise PackagesError("listing libraries timed out") from exc
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
    if proc.returncode != 0:
        raise PackagesError(f"listing libraries failed (exit {proc.returncode})")
    try:
        rows = json.loads(out)
        items = [{"name": str(r["name"]), "version": str(r["version"])} for r in rows]
    except (ValueError, KeyError, TypeError) as exc:
        raise PackagesError("unexpected output from uv pip list") from exc
    return sorted(items, key=lambda i: str(canonicalize_name(i["name"])))
