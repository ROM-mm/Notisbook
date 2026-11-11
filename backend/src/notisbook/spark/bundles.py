"""Compatibility matrix of lakehouse libraries (Delta, Iceberg, Hudi) per Spark line.

Entries cover a `major.minor` line, optionally narrowed to a patch range (the Delta
release that fits a line can depend on the patch). Every jar carries a pinned sha256 so the installer can
verify downloads; bump `revision` whenever an entry changes (`key` is its unique identity, recorded in the kernelspec) so that installed
environments are reported as `outdated`. Versions without an entry have no bundle.
"""

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..catalog.store import catalog_db_path

DEFAULT_MAVEN_URL = "https://repo1.maven.org/maven2"
MAVEN_URL_ENV = "NOTISBOOK_MAVEN_URL"
WAREHOUSE_DIR = "warehouse"
SPARK_WAREHOUSE_SUBDIR = "spark"
_VERSION = re.compile(r"(\d+\.\d+)\.(\d+)", re.ASCII)

EXT_ICEBERG = "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
EXT_DELTA = "io.delta.sql.DeltaSparkSessionExtension"
EXT_HUDI = "org.apache.spark.sql.hudi.HoodieSparkSessionExtension"
# Wait for a lock held by another kernel before failing with "database is locked" (driver default is 3s).
SQLITE_BUSY_TIMEOUT_MS = 10000


class UnsupportedHome(ValueError):
    """`NOTISBOOK_HOME` cannot be embedded in the catalog JDBC URL."""


@dataclass(frozen=True)
class Artifact:
    group: str
    name: str
    version: str
    sha256: str

    @property
    def filename(self) -> str:
        return f"{self.name}-{self.version}.jar"

    @property
    def coordinates(self) -> str:
        return f"{self.group}:{self.name}:{self.version}"


@dataclass(frozen=True)
class Bundle:
    key: str
    line: str
    revision: int
    formats: tuple[str, ...]
    pip: tuple[str, ...]
    artifacts: tuple[Artifact, ...]
    # Jars for the driver JVM classpath (not `spark.jars`): the JDBC catalog finds its driver via DriverManager.
    driver_artifacts: tuple[Artifact, ...] = ()
    min_patch: int = 0
    max_patch: int | None = None

    def covers(self, patch: int) -> bool:
        return patch >= self.min_patch and (self.max_patch is None or patch <= self.max_patch)


SQLITE_JDBC = Artifact(
    "org.xerial",
    "sqlite-jdbc",
    "3.54.1.0",
    "f8dce420a6016278497f4f0560f65602b9db858de141b541cf91a4644ebe4639",
)


MATRIX: dict[str, Bundle] = {
    # Delta 3.2.0 is the last release whose pyspark requirement still admits 3.5.0-3.5.2
    # (3.2.1+ needs pyspark>=3.5.3); Iceberg and Hudi 3.5 runtimes are shared with the 3.5.3+ entry.
    "3.5.0-3.5.2": Bundle(
        key="3.5.0-3.5.2",
        line="3.5",
        revision=3,
        formats=("delta", "iceberg", "hudi"),
        pip=("delta-spark==3.2.0",),
        max_patch=2,
        artifacts=(
            Artifact("io.delta", "delta-spark_2.12", "3.2.0", "51d473537d1bc10c81f48b03d8e2a6b604e1b421a70835ec12e917a4245a31d5"),
            Artifact("io.delta", "delta-storage", "3.2.0", "58aab63eba7736fea9e03eafb0dde6704a34a70f570c1a69ab8e4012c25a95d4"),
            Artifact(
                "org.apache.iceberg",
                "iceberg-spark-runtime-3.5_2.12",
                "1.10.1",
                "39ea09e6c03550a300b9d9ab498949836d2d434e441da4c12a943a086e396940",
            ),
            Artifact(
                "org.apache.hudi",
                "hudi-spark3.5-bundle_2.12",
                "1.2.1",
                "b815831290bb2e9b32001619217e42b5c72c0ca7fb862045c5dc366365de5be2",
            ),
        ),
        driver_artifacts=(SQLITE_JDBC,),
    ),
    # Scala 2.12 builds; Delta 3.3.x is the Delta line built for Spark 3.5.
    "3.5": Bundle(
        key="3.5",
        line="3.5",
        revision=3,
        formats=("delta", "iceberg", "hudi"),
        pip=("delta-spark==3.3.3",),
        min_patch=3,
        artifacts=(
            Artifact("io.delta", "delta-spark_2.12", "3.3.3", "4912bf902a1c453aba3bd838ff212dedd357155212f9bb37a6b47d97f2827ebc"),
            Artifact("io.delta", "delta-storage", "3.3.3", "45ad193053fd30cebe6d9ab1889873cde39b223a0f210e00ebee8b6642476901"),
            Artifact(
                "org.apache.iceberg",
                "iceberg-spark-runtime-3.5_2.12",
                "1.10.1",
                "39ea09e6c03550a300b9d9ab498949836d2d434e441da4c12a943a086e396940",
            ),
            Artifact(
                "org.apache.hudi",
                "hudi-spark3.5-bundle_2.12",
                "1.2.1",
                "b815831290bb2e9b32001619217e42b5c72c0ca7fb862045c5dc366365de5be2",
            ),
        ),
        driver_artifacts=(SQLITE_JDBC,),
    ),
    # Scala 2.13 builds; Delta 4.1.0 is compiled against Spark 4.1.0.
    "4.1": Bundle(
        key="4.1",
        line="4.1",
        revision=3,
        formats=("delta", "iceberg", "hudi"),
        pip=("delta-spark==4.1.0",),
        artifacts=(
            Artifact("io.delta", "delta-spark_2.13", "4.1.0", "9b05d7a82196ee1f1073733a45a2faae59161e52b86ae918fe6742fad6eaf036"),
            Artifact("io.delta", "delta-storage", "4.1.0", "6d0520ffcc35b582369f92c23fa24e14a5bb935cf6e31ed7f47c5046ae17cb25"),
            Artifact(
                "org.apache.iceberg",
                "iceberg-spark-runtime-4.1_2.13",
                "1.12.0",
                "3123c3798af642dd537230923548e013ef41cc28b6626e5225808cf5670a0f82",
            ),
            Artifact(
                "org.apache.hudi",
                "hudi-spark4.1-bundle_2.13",
                "1.2.1",
                "dd4cfcc5994fa4889b98b4c07716db0a46a894d31b714e7a6e6579b89e683bb5",
            ),
        ),
        driver_artifacts=(SQLITE_JDBC,),
    ),
}


def bundle_for(version: str) -> Bundle | None:
    """Bundle whose line and patch range cover the version, or None when the matrix has no entry."""
    match = _VERSION.match(version)
    if match is None:
        return None
    line, patch = match.group(1), int(match.group(2))
    return next((b for b in MATRIX.values() if b.line == line and b.covers(patch)), None)


def maven_url(artifact: Artifact) -> str:
    """Download URL of the jar; the repository base can be overridden by NOTISBOOK_MAVEN_URL."""
    base = (os.environ.get(MAVEN_URL_ENV) or DEFAULT_MAVEN_URL).rstrip("/")
    return f"{base}/{artifact.group.replace('.', '/')}/{artifact.name}/{artifact.version}/{artifact.filename}"


def catalog_uri(home: Path) -> str:
    """JDBC URL of the shared `catalog.db`; `?` in the path would be read as the query start."""
    if "?" in str(home):
        raise UnsupportedHome(f"NOTISBOOK_HOME must not contain '?' (it breaks the catalog JDBC URL): {home}")
    return f"jdbc:sqlite:{catalog_db_path(home)}?busy_timeout={SQLITE_BUSY_TIMEOUT_MS}"


def render_base_defaults(home: Path) -> list[str]:
    """Lines that keep Spark's default warehouse under `home` and the session catalog in memory.

    Without the warehouse line the kernel's cwd (the notebook folder) receives `spark-warehouse/`;
    the in-memory catalog keeps Hive's embedded metastore out of that folder (the persistent
    registry lives in `catalog.db`).
    """
    return [
        f"spark.sql.warehouse.dir {home / WAREHOUSE_DIR / SPARK_WAREHOUSE_SUBDIR}",
        "spark.sql.catalogImplementation in-memory",
    ]


def render_spark_defaults(bundle: Bundle | None, jars_dir: Path, home: Path) -> str:
    """Content of `spark-defaults.conf`; with a bundle it also wires the three formats to the local jars.

    Iceberg lives in the named `iceberg` catalog (JDBC over `catalog.db`): `spark_catalog` stays
    Delta's, since `SparkSessionCatalog` and `DeltaCatalog` cannot share the session catalog slot.
    Raises UnsupportedHome when `home` cannot go into the JDBC URL.
    """
    lines = render_base_defaults(home)
    if bundle is None:
        return "\n".join(lines) + "\n"
    jars = ",".join(str(jars_dir / artifact.filename) for artifact in bundle.artifacts)
    driver_jars = ",".join(str(jars_dir / artifact.filename) for artifact in bundle.driver_artifacts)
    extensions = f"{EXT_ICEBERG},{EXT_DELTA},{EXT_HUDI}"
    lines += [
        f"spark.jars {jars}",
        *([f"spark.driver.extraClassPath {driver_jars}"] if driver_jars else []),
        f"spark.sql.extensions {extensions}",
        "spark.sql.catalog.spark_catalog org.apache.spark.sql.delta.catalog.DeltaCatalog",
        "spark.sql.catalog.iceberg org.apache.iceberg.spark.SparkCatalog",
        "spark.sql.catalog.iceberg.type jdbc",
        f"spark.sql.catalog.iceberg.uri {catalog_uri(home)}",
        f"spark.sql.catalog.iceberg.warehouse {home / WAREHOUSE_DIR / 'iceberg'}",
        "spark.sql.catalog.iceberg.jdbc.schema-version V1",
        # The backend creates the Iceberg tables; the catalog's own init pins a read snapshot in its
        # pooled SQLite connection and breaks the next commit after any external write (BUSY_SNAPSHOT).
        "spark.sql.catalog.iceberg.jdbc.init-catalog-tables false",
        "spark.serializer org.apache.spark.serializer.KryoSerializer",
        "spark.kryo.registrator org.apache.spark.HoodieSparkKryoRegistrar",
    ]
    return "\n".join(lines) + "\n"


# Spark's own log4j2-defaults.properties (identical in 3.5.9 and 4.3.0, except the Hive logger
# that each line quiets) plus the curated filters. A log4j2.properties on the classpath replaces
# the default wholesale, so the defaults must be reproduced; `logger.repl` at warn is what keeps
# the root level from staying at info in a pyspark session.
_LOG4J2_DEFAULTS = """\
rootLogger.level = info
rootLogger.appenderRef.stdout.ref = console

appender.console.type = Console
appender.console.name = console
appender.console.target = SYSTEM_ERR
appender.console.layout.type = PatternLayout
appender.console.layout.pattern = %d{yy/MM/dd HH:mm:ss} %p %c{1}: %m%n%ex

logger.jetty.name = org.sparkproject.jetty
logger.jetty.level = warn
logger.jetty2.name = org.sparkproject.jetty.util.component.AbstractLifeCycle
logger.jetty2.level = error
logger.repl1.name = org.apache.spark.repl.SparkIMain$exprTyper
logger.repl1.level = info
logger.repl2.name = org.apache.spark.repl.SparkILoop$SparkILoopInterpreter
logger.repl2.level = info

logger.repl.name = org.apache.spark.repl.Main
logger.repl.level = warn

logger.metastore.name = org.apache.hadoop.hive.metastore.RetryingHMSHandler
logger.metastore.level = fatal
logger.hive_functionregistry.name = org.apache.hadoop.hive.ql.exec.FunctionRegistry
logger.hive_functionregistry.level = error
logger.metastore2.name = org.apache.hadoop.hive.metastore.ObjectStore
logger.metastore2.level = error

logger.parquet.name = org.apache.parquet.CorruptStatistics
logger.parquet.level = error
logger.parquet2.name = parquet.CorruptStatistics
logger.parquet2.level = error
"""

# Benign warnings denied by message on the console appender, so the other messages of the same
# loggers still show. The filter lives on the appender (not on declared loggers) because a declared
# logger stops following the root level and `setLogLevel`.
_LOG4J2_CURATED = """
appender.console.filter.benign.type = RegexFilter
appender.console.filter.benign.regex = (?s).*(resolves to a loopback address|Set SPARK_LOCAL_IP|Error reading version hint file).*
appender.console.filter.benign.onMatch = DENY
appender.console.filter.benign.onMismatch = NEUTRAL

logger.nativecode.name = org.apache.hadoop.util.NativeCodeLoader
logger.nativecode.level = error
"""

LOG4J2_FILENAME = "log4j2.properties"


def render_log4j2() -> str:
    """Content of `log4j2.properties`: Spark's default configuration plus the curated filters."""
    return _LOG4J2_DEFAULTS + _LOG4J2_CURATED


def write_log4j2(conf_dir: Path) -> bool:
    """Create `conf_dir` and atomically (re)write `log4j2.properties`; True when the file changed."""
    content = render_log4j2()
    target = conf_dir / LOG4J2_FILENAME
    try:
        if target.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    conf_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=conf_dir, prefix=".log4j2.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def write_spark_defaults(conf_dir: Path, content: str) -> bool:
    """Atomically (re)write `spark-defaults.conf` in an existing `conf_dir`; True when the file changed."""
    target = conf_dir / "spark-defaults.conf"
    try:
        if target.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=conf_dir, prefix=".spark-defaults.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True
