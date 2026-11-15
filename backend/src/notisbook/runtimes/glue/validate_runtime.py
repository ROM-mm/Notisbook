"""Valida o runtime Glue do Notisbook de dentro do container.

Uso: docker exec -i <container> python3 - < validate_runtime.py

Imprime um único JSON no stdout com uma entrada por verificação (`ok` e detalhes).
Todo o resto (logs do Spark, avisos) vai para o stderr. Sai com 0 somente se todas
as verificações passarem. Compatível com Python 3.11 (interpretador da imagem Glue 5.0);
roda sem credenciais e sem rede: a sessão Spark usa catálogo `in-memory` e não toca
no Glue Data Catalog da AWS.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from importlib import metadata
from typing import Any

KERNEL_TIMEOUT_S = 60
S3A_FILESYSTEM_CLASS = "org.apache.hadoop.fs.s3a.S3AFileSystem"
# Padrão do Spark para `spark.redaction.regex` quando a conf não está definida.
DEFAULT_REDACTION_REGEX = "(?i)secret|password|token|access.key"
S3A_SENSITIVE_KEYS = ("fs.s3a.bucket.notislake.secret.key", "fs.s3a.bucket.notislake.access.key")
REQUIRED_PACKAGES = ("ipykernel", "jupyter_client", "pyspark")
OPTIONAL_PACKAGES = ("ipython", "pyzmq", "tornado", "traitlets")

Result = dict[str, Any]


def _err(exc: BaseException) -> str:
    first_line = (str(exc).strip().splitlines() or [""])[0]
    return f"{type(exc).__name__}: {first_line}"[:300]


def _guard(fn: Callable[[], Result]) -> Result:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a validação deve reportar qualquer falha, nunca propagá-la
        return {"ok": False, "error": _err(exc)}


def check_python() -> Result:
    return {"ok": True, "version": sys.version.split()[0], "executable": sys.executable}


def check_spark() -> Result:
    spark_home = os.environ.get("SPARK_HOME", "")
    jars = glob.glob(os.path.join(spark_home, "jars", "spark-core_*.jar"))
    if not jars:
        return {"ok": False, "error": f"spark-core jar não encontrado em SPARK_HOME={spark_home!r}"}
    match = re.search(r"spark-core_[\d.]+-(.+)\.jar$", os.path.basename(jars[0]))
    if not match:
        return {"ok": False, "error": f"versão não identificada em {os.path.basename(jars[0])}"}
    return {"ok": True, "version": match.group(1), "home": spark_home}


def check_pyspark() -> Result:
    import pyspark

    return {"ok": True, "version": pyspark.__version__}


def check_java() -> Result:
    proc = subprocess.run(
        ["java", "-version"], capture_output=True, text=True, timeout=30, check=False
    )
    output = proc.stderr or proc.stdout
    match = re.search(r'version "([^"]+)"', output)
    if proc.returncode != 0 or not match:
        return {"ok": False, "error": output.strip()[:200] or f"exit {proc.returncode}"}
    return {"ok": True, "version": match.group(1)}


def check_awsglue() -> Result:
    import awsglue

    return {"ok": True, "path": os.path.dirname(awsglue.__file__)}


def check_packages() -> Result:
    versions: dict[str, str | None] = {}
    for name in REQUIRED_PACKAGES + OPTIONAL_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    missing = [name for name in REQUIRED_PACKAGES if versions[name] is None]
    result: Result = {"ok": not missing, "versions": versions}
    if missing:
        result["error"] = f"ausentes: {', '.join(missing)}"
    return result


def check_sqlite3() -> Result:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('a'), ('b')")
        count = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()
    if count != 2:
        return {"ok": False, "error": f"contagem inesperada: {count}"}
    return {"ok": True, "version": sqlite3.sqlite_version}


def check_ipykernel_exec() -> Result:
    import ipykernel  # noqa: F401 - falha explícita e curta quando a imagem não o traz
    from jupyter_client import KernelManager

    manager = KernelManager(kernel_name="python3")
    client = None
    try:
        manager.start_kernel()
        client = manager.client()
        client.start_channels()
        client.wait_for_ready(timeout=KERNEL_TIMEOUT_S)
        msg_id = client.execute("print(6 * 7)", store_history=False)
        output = _collect_stream(client, msg_id, KERNEL_TIMEOUT_S)
    finally:
        if client is not None:
            client.stop_channels()
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
        manager.cleanup_resources()
    if output.strip() != "42":
        return {"ok": False, "error": f"saída inesperada da célula: {output.strip()[:100]!r}"}
    return {"ok": True, "kernel_name": "python3", "output": output.strip()}


def _collect_stream(client: Any, msg_id: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[str] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("kernel não concluiu a célula no prazo")
        msg = client.get_iopub_msg(timeout=remaining)
        if msg["parent_header"].get("msg_id") != msg_id:
            continue
        msg_type = msg["header"]["msg_type"]
        if msg_type == "stream":
            chunks.append(msg["content"]["text"])
        elif msg_type == "error":
            raise RuntimeError(f"célula falhou: {msg['content'].get('ename')}")
        elif msg_type == "status" and msg["content"]["execution_state"] == "idle":
            return "".join(chunks)


def check_spark_session(state: dict[str, Any]) -> Result:
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[1]")
        .appName("notisbook-validate-runtime")
        .config("spark.sql.catalogImplementation", "in-memory")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    state["spark"] = spark
    catalog = spark.conf.get("spark.sql.catalogImplementation")
    rows = spark.range(10).count()
    ok = catalog == "in-memory" and rows == 10
    result: Result = {"ok": ok, "version": spark.version, "catalogImplementation": catalog}
    if not ok:
        result["error"] = f"catalog={catalog!r} range_count={rows}"
    return result


def check_s3a(state: dict[str, Any]) -> Result:
    spark = state["spark"]
    jvm = spark._jvm
    jvm.java.lang.Class.forName(S3A_FILESYSTEM_CLASS)
    hadoop_version = str(jvm.org.apache.hadoop.util.VersionInfo.getVersion())
    configured = spark.sparkContext.getConf().get("spark.redaction.regex", None)
    regex = configured or DEFAULT_REDACTION_REGEX
    unredacted = [key for key in S3A_SENSITIVE_KEYS if not re.search(regex, key)]
    result: Result = {
        "ok": not unredacted,
        "filesystem": S3A_FILESYSTEM_CLASS,
        "hadoop_version": hadoop_version,
        "redaction_regex": regex,
        "redaction_regex_source": "conf" if configured else "default",
    }
    if unredacted:
        result["error"] = f"chaves sem redação: {', '.join(unredacted)}"
    return result


def check_glue_context(state: dict[str, Any]) -> Result:
    from awsglue.context import GlueContext

    state["glue_context"] = GlueContext(state["spark"].sparkContext)
    return {"ok": True}


def check_dynamicframe(state: dict[str, Any]) -> Result:
    from awsglue.dynamicframe import DynamicFrame

    spark = state["spark"]
    df = spark.createDataFrame([(i, f"n{i}") for i in range(10)], ["id", "name"])
    dyf = DynamicFrame.fromDF(df, state["glue_context"], "validate")
    dyf = dyf.filter(lambda r: r["id"] % 2 == 0)

    def double(record: Any) -> Any:
        record["id2"] = record["id"] * 2
        return record

    dyf = dyf.map(double)
    count = dyf.count()
    total = dyf.toDF().agg({"id2": "sum"}).collect()[0][0]
    ok = count == 5 and total == 40
    result: Result = {"ok": ok, "count": count, "sum_id2": total}
    if not ok:
        result["error"] = f"esperado count=5 sum_id2=40, obtido {count}/{total}"
    return result


def _dependent(state: dict[str, Any], needs: str, fn: Callable[[], Result]) -> Result:
    if needs not in state:
        return {"ok": False, "error": f"não executado: depende de {needs}"}
    return _guard(fn)


def run_checks() -> dict[str, Result]:
    state: dict[str, Any] = {}
    results: dict[str, Result] = {
        "python": _guard(check_python),
        "spark": _guard(check_spark),
        "pyspark": _guard(check_pyspark),
        "java": _guard(check_java),
        "awsglue": _guard(check_awsglue),
        "packages": _guard(check_packages),
        "sqlite3": _guard(check_sqlite3),
        "ipykernel_exec": _guard(check_ipykernel_exec),
        "spark_session": _guard(lambda: check_spark_session(state)),
    }
    results["s3a"] = _dependent(state, "spark", lambda: check_s3a(state))
    results["glue_context"] = _dependent(state, "spark", lambda: check_glue_context(state))
    results["dynamicframe"] = _dependent(
        state, "glue_context", lambda: check_dynamicframe(state)
    )
    if "spark" in state:
        try:
            state["spark"].stop()
        except Exception as exc:  # noqa: BLE001 - falha ao encerrar não invalida os resultados já obtidos
            print(f"spark.stop falhou: {_err(exc)}", file=sys.stderr)
    return results


def main() -> int:
    # Filhos (JVM, kernel) herdam o fd 1: redireciona-o ao stderr e guarda o stdout real.
    real_stdout = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    results = run_checks()
    real_stdout.write(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    real_stdout.flush()
    return 0 if all(r.get("ok") is True for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
