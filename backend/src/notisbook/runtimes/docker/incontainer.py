"""Código executado DENTRO do container do runtime (Python 3.11, só biblioteca padrão).

Enviado pelo stdin de `docker exec -i`; nunca importado pelo app. Modos (argv após o nome do script):
  run <tag> [--cwd DIR] [--warehouse-dir DIR] [--iceberg-uri URI --iceberg-warehouse DIR]
                         [--s3a-closed JSON]
                         lê o connection file (JSON) do stdin, encerra o kernel anterior de <tag>,
                         vira líder de grupo, grava PID+starttime em /run/notisbook e faz exec do ipykernel
  kill <tag>             SIGKILL no grupo do kernel de <tag> (validando PID+starttime)
  sweep                  `kill` para todas as tags registradas
  packages               JSON com a versão do Python e as distribuições instaladas
Saída 0 em sucesso; 2 uso inválido; 3 falha ao preparar o processo; 4 conn file inválido.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import signal
import sys
import time
from importlib import metadata
from typing import NoReturn

RUN_DIR = "/run/notisbook"
TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
CONN_PORTS = ("shell_port", "iopub_port", "stdin_port", "control_port", "hb_port")
KILL_WAIT_S = 5.0
RUN_OPTIONS = {"--cwd", "--warehouse-dir", "--iceberg-uri", "--iceberg-warehouse", "--s3a-closed"}
# Warehouse do Iceberg: só a raiz do bucket; espelha `notislake.locations.ROOT_URI` (o incontainer não importa `notisbook.*`).
ICEBERG_WAREHOUSE_URI = "s3a://notislake"
# Warehouse local de segurança do `spark_catalog`: `file:` absoluto, sem `..`, aspas, vírgula ou controle.
LOCAL_WAREHOUSE_RE = re.compile(r"file:/[^\x00-\x1f\x7f\"',]{1,500}")
# Config fechada do bucket vinda do launch (`sparkconf.closed_options()`): chave por bucket e valor simples.
S3A_KEY_RE = re.compile(r"fs\.s3a\.bucket\.notislake\.[a-z][a-z0-9.]{0,80}")
S3A_VALUE_RE = re.compile(r"[A-Za-z0-9:./_-]{1,200}")
S3A_FORBIDDEN = ("secret", "access.key", "token")
ICEBERG_URI_RE = re.compile(r"http://[A-Za-z0-9.-]+:[0-9]{1,5}/iceberg")
SUBMIT_ARGS = (
    "--conf spark.sql.catalogImplementation=in-memory "
    "--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
    "io.delta.sql.DeltaSparkSessionExtension,"
    "org.apache.spark.sql.hudi.HoodieSparkSessionExtension "
    "--conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog "
    # O Hudi exige Kryo; mesma ordem de extensões e registrator do runtime Spark local (`spark/bundles.py`).
    "--conf spark.serializer=org.apache.spark.serializer.KryoSerializer "
    "--conf spark.kryo.registrator=org.apache.spark.HoodieSparkKryoRegistrar "
    "pyspark-shell"
)
PYSPARK_SHELL = "pyspark-shell"
# Config de log do driver: só erros chegam à saída da célula, como no Spark local (`spark.bundles.render_log4j2`).
# Raiz e os loggers do limiar do shell em `error`: o Spark imprime "Setting default log level" quando diferem.
LOG4J2_PATH = os.path.join(RUN_DIR, "jvm-log4j2.properties")
LOG4J2_CONF = """\
rootLogger.level = error
rootLogger.appenderRef.stdout.ref = console

appender.console.type = Console
appender.console.name = console
appender.console.target = SYSTEM_ERR
appender.console.layout.type = PatternLayout
appender.console.layout.pattern = %d{yy/MM/dd HH:mm:ss} %p %c{1}: %m%n%ex

logger.repl.name = org.apache.spark.repl.Main
logger.repl.level = error
logger.pygateway.name = org.apache.spark.api.python.PythonGatewayServer
logger.pygateway.level = error
"""
DELTA_JAR_GLOBS = ("/usr/share/aws/delta/lib/delta-spark_2.12-*.jar", "/usr/share/aws/delta/lib/delta-spark.jar")


def _parse_s3a_closed(raw: str) -> dict[str, str] | None:
    """Config fechada do bucket do `--s3a-closed`; None se não for JSON de chaves/valores simples sem segredo."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    for key, value in data.items():
        if not (isinstance(key, str) and isinstance(value, str)):
            return None
        if not (S3A_KEY_RE.fullmatch(key) and S3A_VALUE_RE.fullmatch(value)):
            return None
        if any(word in key for word in S3A_FORBIDDEN):
            return None
    return data


def _submit_args(
    warehouse_dir: str | None,
    iceberg_uri: str | None = None,
    iceberg_warehouse: str | None = None,
    s3a_closed: dict[str, str] | None = None,
) -> str:
    """SUBMIT_ARGS com o warehouse e o catálogo `iceberg` (REST) do app; o PySpark separa a variável com shlex.

    Sem segredos: o token do catálogo e a credencial S3A entram depois, pelo hook do kernel (nunca no `ps`).
    """
    confs = [f"spark.hadoop.{key}={value}" for key, value in (s3a_closed or {}).items()]
    if warehouse_dir:
        confs.append(f"spark.sql.warehouse.dir={warehouse_dir}")
    if iceberg_uri and iceberg_warehouse:
        prefix = "spark.sql.catalog.iceberg"
        confs += [
            f"{prefix}=org.apache.iceberg.spark.SparkCatalog",
            f"{prefix}.type=rest",
            f"{prefix}.uri={iceberg_uri}",
            f"{prefix}.warehouse={iceberg_warehouse}",
            f"{prefix}.token-refresh-enabled=false",
            f"{prefix}.oauth2-server-uri={iceberg_uri}/v1/oauth/tokens",
        ]
    head = SUBMIT_ARGS[: -len(PYSPARK_SHELL)]
    return head + "".join(f"--conf {shlex.quote(conf)} " for conf in confs) + PYSPARK_SHELL


def _kernel_env() -> None:
    """Ajusta o ambiente do kernel: `delta.tables` e falha rápida do Glue Data Catalog remoto (fora de escopo).

    O módulo Python `delta` só existe dentro do jar do delta-spark da imagem (zipimport); resolvido por glob para não
    fixar a versão. Sem AWS, a cadeia de credenciais do SDK Java/botocore esperava o IMDS (50 tentativas na imagem).
    """
    for pattern in DELTA_JAR_GLOBS:
        if jars := sorted(glob.glob(pattern)):
            parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
            os.environ["PYTHONPATH"] = os.pathsep.join([*parts, jars[-1]])
            break
    os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    os.environ.setdefault("AWS_METADATA_SERVICE_NUM_ATTEMPTS", "1")


def _jvm_logging() -> None:
    """Aponta o driver para a config log4j2 acima, via `SPARK_SUBMIT_OPTS`.

    Via env (e não `spark.driver.extraJavaOptions`) para não substituir as opções da imagem (truststore). O arquivo
    vai por este caminho, sem montagem nova, e é regravado a cada kernel; sem ele o log fica como o da imagem.
    """
    tmp = f"{LOG4J2_PATH}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(LOG4J2_CONF)
        os.replace(tmp, LOG4J2_PATH)
    except OSError:
        _unlink(tmp)
        sys.stderr.write("notisbook-incontainer: config de log indisponível; usando a da imagem\n")
        return
    option = f"-Dlog4j2.configurationFile=file:{LOG4J2_PATH}"
    current = os.environ.get("SPARK_SUBMIT_OPTS", "")
    os.environ["SPARK_SUBMIT_OPTS"] = f"{option} {current}" if current else option


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


def cmd_run(tag: str, options: dict[str, str]) -> None:
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
    if cwd := options.get("--cwd"):
        try:
            os.chdir(cwd)
        except OSError:
            sys.stderr.write(
                "notisbook-incontainer: pasta do notebook indisponível no container; usando a padrão\n"
            )
    _kernel_env()
    _jvm_logging()
    os.environ["PYSPARK_SUBMIT_ARGS"] = _submit_args(
        options.get("--warehouse-dir"),
        options.get("--iceberg-uri"),
        options.get("--iceberg-warehouse"),
        _parse_s3a_closed(options["--s3a-closed"]) if "--s3a-closed" in options else None,
    )
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


def _run_options(rest: list[str]) -> dict[str, str] | None:
    """Pares `--opção valor` do `run` (sem repetição); None se algo fora disso ou valor inválido."""
    if len(rest) % 2:
        return None
    options = dict(zip(rest[::2], rest[1::2]))
    if len(options) * 2 != len(rest) or not set(options) <= RUN_OPTIONS:
        return None
    warehouse = options.get("--warehouse-dir")
    if warehouse is not None and not (
        LOCAL_WAREHOUSE_RE.fullmatch(warehouse) and ".." not in warehouse.split("/")
    ):
        return None
    if options.get("--iceberg-warehouse", ICEBERG_WAREHOUSE_URI) != ICEBERG_WAREHOUSE_URI:
        return None
    if "--s3a-closed" in options and _parse_s3a_closed(options["--s3a-closed"]) is None:
        return None
    if ("--iceberg-uri" in options) != ("--iceberg-warehouse" in options):
        return None
    if "--iceberg-uri" in options and not ICEBERG_URI_RE.fullmatch(options["--iceberg-uri"]):
        return None
    return options


def main(argv: list[str]) -> None:
    mode = argv[0] if argv else ""
    options = _run_options(argv[2:]) if mode == "run" and len(argv) >= 2 else None
    if options is not None:
        cmd_run(_valid_tag(argv[1]), options)
    elif mode == "kill" and len(argv) == 2:
        sys.stdout.write("killed\n" if kill_tag(_valid_tag(argv[1])) else "none\n")
    elif mode == "sweep" and len(argv) == 1:
        sys.stdout.write(f"{sum(kill_tag(tag) for tag in _tags())}\n")
    elif mode == "packages" and len(argv) == 1:
        cmd_packages()
    else:
        _fail(
            2,
            "uso: run <tag> [--cwd DIR] [--warehouse-dir DIR] [--iceberg-uri URI --iceberg-warehouse DIR]"
            " [--s3a-closed JSON]"
            " | kill <tag> | sweep | packages",
        )


if __name__ == "__main__":
    main(sys.argv[1:])
