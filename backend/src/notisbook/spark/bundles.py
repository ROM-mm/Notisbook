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
# Warehouse de segurança do `spark_catalog` (escrita que escapa da regra do notislake). No Docker só existe o que já
# está montado no container (`warehouse/`); no local o kernel usa uma pasta própria do home (`spark-warehouse/`).
WAREHOUSE_DIR = "warehouse"
SAFETY_WAREHOUSE_DIR = "spark-warehouse"
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
    # Hadoop line that the jars of `driver_artifacts` were built against (the pyspark wheel bundles the same one).
    hadoop: str = ""
    # Class that only exists in the AWS SDK jar of this bundle; the smoke test loads it to prove the SDK is wired.
    sdk_probe_class: str = ""
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

# S3A jars must match the Hadoop that ships inside each pyspark line; mixing versions breaks S3AFileSystem.
HADOOP_35 = "3.3.4"
HADOOP_41 = "3.4.2"
S3A_35 = (
    Artifact("org.apache.hadoop", "hadoop-aws", HADOOP_35, "53f9ae03c681a30a50aa17524bd9790ab596b28481858e54efd989a826ed3a4a"),
    Artifact("com.amazonaws", "aws-java-sdk-bundle", "1.12.262", "873fe7cf495126619997bec21c44de5d992544aea7e632fdc77adb1a0915bae5"),
    Artifact("org.wildfly.openssl", "wildfly-openssl", "1.0.7.Final", "9f7058778978ec2ad90c7224401a4b0013d93e0dd3fa0f72b25244ffa3507ca8"),
)
S3A_41 = (
    Artifact("org.apache.hadoop", "hadoop-aws", HADOOP_41, "d2d24e6b715b5656b9d238bf13b6682a07e2004dd36aad74a73aeb854319f4d9"),
    Artifact("software.amazon.awssdk", "bundle", "2.29.52", "62638f33045690c6bc5e496b54b0b2e89a9ad38cbedacdf6e017fea6bc85f55c"),
    Artifact("org.wildfly.openssl", "wildfly-openssl", "2.1.4.Final", "95decbc5d088b40e85f58d7726b8c8f4e3be6312a0f2660c2d714a23cee80279"),
)
SDK_PROBE_35 = "com.amazonaws.services.s3.AmazonS3"
SDK_PROBE_41 = "software.amazon.awssdk.services.s3.S3Client"


MATRIX: dict[str, Bundle] = {
    # Delta 3.2.0 is the last release whose pyspark requirement still admits 3.5.0-3.5.2
    # (3.2.1+ needs pyspark>=3.5.3); Iceberg and Hudi 3.5 runtimes are shared with the 3.5.3+ entry.
    "3.5.0-3.5.2": Bundle(
        key="3.5.0-3.5.2",
        line="3.5",
        revision=4,
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
        driver_artifacts=(SQLITE_JDBC, *S3A_35),
        hadoop=HADOOP_35,
        sdk_probe_class=SDK_PROBE_35,
    ),
    # Scala 2.12 builds; Delta 3.3.x is the Delta line built for Spark 3.5.
    "3.5": Bundle(
        key="3.5",
        line="3.5",
        revision=4,
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
        driver_artifacts=(SQLITE_JDBC, *S3A_35),
        hadoop=HADOOP_35,
        sdk_probe_class=SDK_PROBE_35,
    ),
    # Scala 2.13 builds; Delta 4.1.0 is compiled against Spark 4.1.0.
    "4.1": Bundle(
        key="4.1",
        line="4.1",
        revision=4,
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
        driver_artifacts=(SQLITE_JDBC, *S3A_41),
        hadoop=HADOOP_41,
        sdk_probe_class=SDK_PROBE_41,
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


def safety_warehouse_uri(home: Path) -> str:
    """Warehouse local do `spark_catalog`: escrita que escapa da regra do notislake cai no disco, não no bucket."""
    return f"file:{home / SAFETY_WAREHOUSE_DIR}"


def docker_safety_warehouse_uri(home: Path) -> str:
    """Warehouse de segurança no container: a pasta `warehouse/` do `home`, montada no mesmo caminho do host."""
    return f"file:{home / WAREHOUSE_DIR}"


def render_base_defaults() -> list[str]:
    """Lines every managed env gets: the session catalog stays in memory.

    Hive's embedded metastore would otherwise create its files in the kernel's cwd (the notebook folder);
    the persistent registry lives in `catalog.db`. The warehouse and the S3A options are NOT here: they
    only make sense with a bundle that ships the S3A jars (see `render_s3a_defaults`).
    """
    return ["spark.sql.catalogImplementation in-memory"]


def render_s3a_defaults(home: Path) -> list[str]:
    """Local safety warehouse plus the closed S3A config (dead endpoint, no secret).

    The real connection is applied by the session hook after `getOrCreate`. Without the warehouse line the
    notebook folder would receive `spark-warehouse/`.
    """
    # Lazy import: `notislake.sparkconf` pulls `config`, which imports this module at load time.
    from ..notislake.sparkconf import closed_options

    return [
        f"spark.sql.warehouse.dir {safety_warehouse_uri(home)}",
        *(f"spark.hadoop.{key} {value}" for key, value in closed_options().items()),
    ]


def render_spark_defaults(bundle: Bundle | None, jars_dir: Path, home: Path) -> str:
    """Content of `spark-defaults.conf`; with a bundle it also wires the three formats, the safety warehouse and the S3A bucket root for Iceberg.

    Without a bundle (no S3A jars) no `s3a://` or `fs.s3a` line is written: such an env is refused at open.

    Iceberg lives in the named `iceberg` catalog (JDBC over `catalog.db`): `spark_catalog` stays
    Delta's, since `SparkSessionCatalog` and `DeltaCatalog` cannot share the session catalog slot.
    Raises UnsupportedHome when `home` cannot go into the JDBC URL.
    """
    from ..notislake.locations import ROOT_URI

    lines = render_base_defaults()
    if bundle is None:
        return "\n".join(lines) + "\n"
    lines += render_s3a_defaults(home)
    jars = ",".join(str(jars_dir / artifact.filename) for artifact in bundle.artifacts)
    # JVM classpath, not a Spark list: entries are separated by the platform path separator, unlike `spark.jars`.
    driver_jars = os.pathsep.join(str(jars_dir / artifact.filename) for artifact in bundle.driver_artifacts)
    extensions = f"{EXT_ICEBERG},{EXT_DELTA},{EXT_HUDI}"
    lines += [
        f"spark.jars {jars}",
        *([f"spark.driver.extraClassPath {driver_jars}"] if driver_jars else []),
        f"spark.sql.extensions {extensions}",
        "spark.sql.catalog.spark_catalog org.apache.spark.sql.delta.catalog.DeltaCatalog",
        "spark.sql.catalog.iceberg org.apache.iceberg.spark.SparkCatalog",
        "spark.sql.catalog.iceberg.type jdbc",
        f"spark.sql.catalog.iceberg.uri {catalog_uri(home)}",
        f"spark.sql.catalog.iceberg.warehouse {ROOT_URI}",
        # Tables live in the shared bucket: Iceberg must not garbage-collect files on its own.
        "spark.sql.catalog.iceberg.table-default.gc.enabled false",
        "spark.sql.catalog.iceberg.jdbc.schema-version V1",
        # Data files go through Hadoop's FileSystem (local and `s3a://`); the default S3FileIO would need the SDK's own wiring.
        "spark.sql.catalog.iceberg.io-impl org.apache.iceberg.hadoop.HadoopFileIO",
        # The backend creates the Iceberg tables; the catalog's own init pins a read snapshot in its
        # pooled SQLite connection and breaks the next commit after any external write (BUSY_SNAPSHOT).
        "spark.sql.catalog.iceberg.jdbc.init-catalog-tables false",
        "spark.serializer org.apache.spark.serializer.KryoSerializer",
        "spark.kryo.registrator org.apache.spark.HoodieSparkKryoRegistrar",
    ]
    return "\n".join(lines) + "\n"


# Spark's own log4j2-defaults.properties (identical in 3.5.9 and 4.3.0, except the Hive logger
# that each line quiets) plus the curated filters. A log4j2.properties on the classpath replaces
# the default wholesale, so the defaults must be reproduced. Unlike Spark's defaults, root and
# `logger.pygateway`/`logger.repl` are set to error: the JVM shares the kernel's stderr, so lower
# levels would surface as output of the last executed cell. PySpark's threshold logger is
# `PythonGatewayServer`: Spark prints the "Setting default log level" lines to System.err when its
# level differs from root, so it must always equal rootLogger.level. `repl.Main` is spark-shell.
_LOG4J2_DEFAULTS = """\
rootLogger.level = error
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
logger.repl.level = error
logger.pygateway.name = org.apache.spark.api.python.PythonGatewayServer
logger.pygateway.level = error

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
