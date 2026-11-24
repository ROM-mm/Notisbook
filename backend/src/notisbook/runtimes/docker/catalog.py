"""Catálogo fixo dos runtimes Docker suportados (só o AWS Glue mais recente; a versão fica no rótulo e na tag da imagem)."""

from dataclasses import dataclass
from pathlib import Path

RUNTIMES_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class DockerRuntime:
    key: str
    label: str
    context_dir: Path
    dockerfile: str
    image: str
    container: str
    kernel_name: str
    formats: tuple[str, ...]

    @property
    def dockerfile_path(self) -> Path:
        return self.context_dir / self.dockerfile


CATALOG: tuple[DockerRuntime, ...] = (
    DockerRuntime(
        key="glue",
        label="AWS Glue 6.0",
        context_dir=RUNTIMES_DIR / "glue",
        dockerfile="Dockerfile",
        image="notisbook/glue:6.0",
        container="notisbook-glue",
        kernel_name="notisbook-docker-glue",
        formats=("delta", "iceberg", "hudi"),
    ),
)


def get(key: str) -> DockerRuntime | None:
    return next((runtime for runtime in CATALOG if runtime.key == key), None)


def by_kernel_name(name: str) -> DockerRuntime | None:
    return next((runtime for runtime in CATALOG if runtime.kernel_name == name), None)
