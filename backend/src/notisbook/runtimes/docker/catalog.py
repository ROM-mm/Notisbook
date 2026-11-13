"""Catálogo fixo dos runtimes Docker suportados (hoje só AWS Glue 5.0)."""

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
        key="glue-5.0",
        label="AWS Glue 5.0",
        context_dir=RUNTIMES_DIR / "glue",
        dockerfile="Dockerfile",
        image="notisbook/glue:5.0",
        container="notisbook-glue-5-0",
        kernel_name="notisbook-docker-glue-5-0",
        formats=("delta",),
    ),
)


def get(key: str) -> DockerRuntime | None:
    return next((runtime for runtime in CATALOG if runtime.key == key), None)


def by_kernel_name(name: str) -> DockerRuntime | None:
    return next((runtime for runtime in CATALOG if runtime.kernel_name == name), None)
