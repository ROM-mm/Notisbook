"""Lançamento do kernel no container e chamadas ao `incontainer.py`.

Como comando (`python -m notisbook.runtimes.docker.launch --key K -f <connection_file>`) é o `argv` do
kernelspec: inicia o container se preciso e faz `exec` de `docker exec -i`, entregando pelo stdin o
`incontainer.py` e o connection file (a pasta de conexões do Mac não é montada). A tag do kernel
é o nome do connection file, estável entre restarts, o que permite ao `run` matar o kernel anterior.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from ...config import RUNTIME_HOST
from ...notislake.sparkconf import closed_options
from . import catalog, cli

# Porta do backend para o container alcançar o Glue do app (`/glue`); o KernelService a põe no env do kernel.
PORT_ENV = "NOTISBOOK_RUNTIME_PORT"
START_TIMEOUT_S = 60.0
CALL_TIMEOUT_S = 30.0
INCONTAINER = Path(__file__).with_name("incontainer.py")
# Lê "<n>\n<n bytes de código>" do stdin e executa; o que sobra (connection file) fica para o código.
BOOTSTRAP = (
    "import sys;n=int(sys.stdin.buffer.readline());"
    "exec(compile(sys.stdin.buffer.read(n),'incontainer','exec'))"
)


class LaunchError(RuntimeError):
    """Container indisponível ou chamada ao incontainer fracassada."""


def tag_for(connection_file: str) -> str:
    """Tag de kernel derivada do nome do connection file (aceita pelo `incontainer`)."""
    tag = re.sub(r"[^A-Za-z0-9_.-]", "-", Path(connection_file).stem).lstrip("-._")
    return tag[-80:] or "kernel"


def glue_options(runtime: catalog.DockerRuntime) -> list[str]:
    """Endpoint Glue do app (`/glue`) só para o runtime Glue; os demais runtimes devolvem vazio.

    Hoje todo runtime Docker do catálogo é Glue, e o `incontainer` exige `--glue-uri`: `_run_options` recusa a linha
    de comando sem um valor que case com `GLUE_URI_RE`. Um runtime Docker que devolvesse vazio aqui só falharia dentro
    do container, não ao montar o comando.
    O container não recebe credencial por aqui: o hook a grava no tmpfs (`catalog_hook.write_glue_credentials`).
    Levanta `LaunchError` no runtime Glue sem porta válida do backend: sem o `/glue` o kernel não tem catálogo.
    """
    if runtime.key != "glue":
        return []
    port = os.environ.get(PORT_ENV, "")
    if not (port.isascii() and port.isdigit() and 0 < int(port) < 65536):
        raise LaunchError(f"o runtime Glue precisa da porta do backend ({PORT_ENV}) para alcançar o catálogo Glue")
    return ["--glue-uri", f"http://{RUNTIME_HOST}:{int(port)}/glue"]


def incontainer_source() -> bytes:
    return INCONTAINER.read_bytes()


def ensure_started(
    runtime: catalog.DockerRuntime, timeout: float = START_TIMEOUT_S
) -> None:
    """`docker start` (idempotente: container já rodando é sucesso)."""
    result = cli.run(["start", runtime.container], timeout=timeout)
    if result.returncode != 0:
        raise LaunchError(f"não foi possível iniciar o container {runtime.container}")


def call(
    runtime: catalog.DockerRuntime,
    mode: str,
    *args: str,
    timeout: float = CALL_TIMEOUT_S,
) -> cli.CliResult:
    """Executa `incontainer.py <mode> <args>` no container; o código viaja pelo stdin."""
    argv = ["exec", "-i", runtime.container, "python3", "-", mode, *args]
    return cli.run(
        argv, timeout=timeout, input_text=incontainer_source().decode("utf-8")
    )


def kill_kernel(runtime: catalog.DockerRuntime, tag: str) -> bool:
    """Mata o kernel de `tag` (grupo inteiro); True se havia um vivo."""
    result = call(runtime, "kill", tag)
    if result.returncode != 0:
        raise LaunchError("falha ao encerrar o kernel no container")
    return result.stdout.strip() == "killed"


def sweep(runtime: catalog.DockerRuntime) -> int:
    """Mata todos os kernels registrados no container; devolve quantos estavam vivos."""
    result = call(runtime, "sweep")
    if result.returncode != 0:
        raise LaunchError("falha ao varrer kernels no container")
    try:
        return int(result.stdout.strip() or 0)
    except ValueError as exc:
        raise LaunchError("resposta inválida do sweep") from exc


def packages(runtime: catalog.DockerRuntime) -> dict[str, Any]:
    result = call(runtime, "packages")
    if result.returncode != 0:
        raise LaunchError("falha ao listar pacotes no container")
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise LaunchError("lista de pacotes inválida") from exc
    if not isinstance(data, dict):
        raise LaunchError("lista de pacotes inválida")
    return data


def launch(key: str, connection_file: str) -> None:
    """Inicia o container se necessário e substitui este processo por `docker exec` (só retorna em erro)."""
    runtime = catalog.get(key)
    if runtime is None:
        raise LaunchError("runtime desconhecido")
    glue = glue_options(runtime)  # antes de iniciar o container: sem a porta do backend o runtime Glue não sobe
    ensure_started(runtime)
    binary = cli.docker_binary()
    if binary is None:
        raise LaunchError("CLI docker não encontrado no PATH")
    source = incontainer_source()
    header = f"{len(source)}\n".encode("ascii")
    argv = [
        binary,
        "exec",
        "-i",
        runtime.container,
        "python3",
        "-c",
        BOOTSTRAP,
        "run",
        tag_for(connection_file),
    ]
    argv += [
        "--cwd",
        os.getcwd(),
        *glue,
        "--s3a-closed",
        json.dumps(closed_options(), sort_keys=True),
    ]
    # Arquivo anônimo 0600 como stdin: o payload (código + connection file) passa de um pipe pequeno.
    with tempfile.TemporaryFile() as payload:
        payload.write(header + source + Path(connection_file).read_bytes())
        payload.flush()
        payload.seek(0)
        os.dup2(payload.fileno(), 0)
        os.execv(binary, argv)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="launch")
    parser.add_argument("--key", required=True)
    parser.add_argument("-f", "--connection-file", required=True)
    options = parser.parse_args(argv)
    try:
        launch(options.key, options.connection_file)
    except (LaunchError, cli.DockerError, OSError) as exc:
        sys.stderr.write(f"notisbook: {exc}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
