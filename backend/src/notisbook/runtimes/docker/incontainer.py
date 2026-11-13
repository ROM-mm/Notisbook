"""Código executado DENTRO do container do runtime (Python 3.11, só biblioteca padrão).

Enviado pelo stdin de `docker exec -i`; nunca importado pelo app. Modos (argv após o nome do script):
  run <tag> [--cwd DIR]  lê o connection file (JSON) do stdin, encerra o kernel anterior de <tag>,
                         vira líder de grupo, grava PID+starttime em /run/notisbook e faz exec do ipykernel
  kill <tag>             SIGKILL no grupo do kernel de <tag> (validando PID+starttime)
  sweep                  `kill` para todas as tags registradas
  packages               JSON com a versão do Python e as distribuições instaladas
Saída 0 em sucesso; 2 uso inválido; 3 falha ao preparar o processo; 4 conn file inválido.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from importlib import metadata
from typing import NoReturn

RUN_DIR = "/run/notisbook"
TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
CONN_PORTS = ("shell_port", "iopub_port", "stdin_port", "control_port", "hb_port")
KILL_WAIT_S = 5.0
SUBMIT_ARGS = (
    "--conf spark.sql.catalogImplementation=in-memory "
    "--conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension "
    "--conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog "
    "pyspark-shell"
)


def _fail(code: int, message: str) -> NoReturn:
    sys.stderr.write(f"notisbook-incontainer: {message}\n")
    sys.exit(code)


def _pid_path(tag: str) -> str:
    return os.path.join(RUN_DIR, f"{tag}.pid")


def _conn_path(tag: str) -> str:
    return os.path.join(RUN_DIR, f"{tag}.json")


def _stat_fields(pid: int) -> list[str] | None:
    """Campos de /proc/<pid>/stat a partir do estado (campo 3); o nome do comando pode conter espaços e ')'."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
            data = handle.read()
    except OSError:
        return None
    return data[data.rfind(")") + 2 :].split()


def _start_time(pid: int) -> int | None:
    fields = _stat_fields(pid)
    if fields is None or len(fields) < 20 or fields[0] == "Z":
        return None
    return int(fields[19])  # campo 22 de /proc/<pid>/stat


def _read_record(tag: str) -> tuple[int, int] | None:
    try:
        with open(_pid_path(tag), encoding="utf-8") as handle:
            pid_text, start_text = handle.read().split()
        return int(pid_text), int(start_text)
    except (OSError, ValueError):
        return None


def _write_atomic(path: str, content: str) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def kill_tag(tag: str) -> bool:
    """Mata o grupo do kernel de `tag` se PID+starttime ainda conferem; devolve True se havia kernel vivo."""
    record = _read_record(tag)
    killed = False
    if record is not None:
        pid, start = record
        if _start_time(pid) == start:
            try:
                target_is_leader = os.getpgid(pid) == pid
                if target_is_leader:
                    os.killpg(pid, signal.SIGKILL)
                else:  # nunca atingir um grupo que não é do kernel
                    os.kill(pid, signal.SIGKILL)
                killed = True
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + KILL_WAIT_S
            while _start_time(pid) == start and time.monotonic() < deadline:
                time.sleep(0.02)
            if _start_time(pid) == start:
                _fail(3, f"kernel {tag} não encerrou em {KILL_WAIT_S:g}s")
    _unlink(_pid_path(tag))
    _unlink(_conn_path(tag))
    return killed


def _tags() -> list[str]:
    try:
        names = os.listdir(RUN_DIR)
    except FileNotFoundError:
        return []
    return sorted(
        n[:-4] for n in names if n.endswith(".pid") and TAG_RE.fullmatch(n[:-4])
    )


def _valid_tag(value: str) -> str:
    if not TAG_RE.fullmatch(value):
        _fail(2, "tag inválida")
    return value


def _read_connection() -> dict[str, object]:
    try:
        conn = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError:
        _fail(4, "connection file ausente ou não é JSON")
    if not isinstance(conn, dict) or not all(
        isinstance(conn.get(k), int) for k in CONN_PORTS
    ):
        _fail(4, "connection file sem as cinco portas")
    if not all(isinstance(conn.get(k), str) for k in ("ip", "transport", "key")):
        _fail(4, "connection file sem ip/transport/key")
    return conn


def cmd_run(tag: str, cwd: str | None) -> None:
    conn = _read_connection()
    kill_tag(tag)
    try:
        os.setsid()
    except PermissionError:
        pass  # `docker exec` já nasce líder de sessão/grupo (pid == pgid == sid)
    if os.getpgid(0) != os.getpid():
        _fail(3, "processo não é líder de grupo; não é possível registrar o kernel")
    start = _start_time(os.getpid())
    if start is None:
        _fail(3, "starttime do processo indisponível")
    os.makedirs(RUN_DIR, exist_ok=True)
    _write_atomic(_conn_path(tag), json.dumps(conn))
    _write_atomic(_pid_path(tag), f"{os.getpid()} {start}\n")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    if cwd:
        try:
            os.chdir(cwd)
        except OSError:
            sys.stderr.write(
                "notisbook-incontainer: pasta do notebook indisponível no container; usando a padrão\n"
            )
    os.environ["PYSPARK_SUBMIT_ARGS"] = SUBMIT_ARGS
    try:
        os.execv(
            sys.executable,
            [sys.executable, "-m", "ipykernel_launcher", "-f", _conn_path(tag)],
        )
    except OSError as exc:
        _unlink(_pid_path(tag))
        _unlink(_conn_path(tag))
        _fail(3, f"exec do ipykernel falhou: {type(exc).__name__}")


def cmd_packages() -> None:
    packages = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            packages[name.lower()] = {"name": name, "version": dist.version}
    payload = {
        "python": sys.version.split()[0],
        "packages": [packages[key] for key in sorted(packages)],
    }
    sys.stdout.write(json.dumps(payload) + "\n")


def main(argv: list[str]) -> None:
    mode = argv[0] if argv else ""
    if mode == "run" and len(argv) in (2, 4) and (len(argv) == 2 or argv[2] == "--cwd"):
        cmd_run(_valid_tag(argv[1]), argv[3] if len(argv) == 4 else None)
    elif mode == "kill" and len(argv) == 2:
        sys.stdout.write("killed\n" if kill_tag(_valid_tag(argv[1])) else "none\n")
    elif mode == "sweep" and len(argv) == 1:
        sys.stdout.write(f"{sum(kill_tag(tag) for tag in _tags())}\n")
    elif mode == "packages" and len(argv) == 1:
        cmd_packages()
    else:
        _fail(2, "uso: run <tag> [--cwd DIR] | kill <tag> | sweep | packages")


if __name__ == "__main__":
    main(sys.argv[1:])
