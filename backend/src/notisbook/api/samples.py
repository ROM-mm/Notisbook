"""Exemplos empacotados que ainda existem na raiz de notebooks atual."""

import json
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..kernels.service import DUCKDB_KERNEL_NAME, DUCKDB_METADATA_KEY, runtime_kind
from ..notebooks.store import NotebookStore, StoreError
from ..onboarding import SAMPLES_DIR
from ..security import require_token, require_trusted_host

# Exemplos exibidos na Home, na ordem de exibição; os demais empacotados são semeados mas não listados.
FEATURED_SAMPLES: tuple[str, ...] = (
    "spark/delta.ipynb",
    "duckdb/duckdb.ipynb",
    "glue/iceberg.ipynb",
)

router = APIRouter(
    prefix="/api/samples",
    dependencies=[Depends(require_token), Depends(require_trusted_host)],
)


def _kernelspec(rel: str) -> dict[str, Any]:
    """`metadata.kernelspec` do exemplo empacotado (fonte da verdade), nunca da cópia do usuário.

    `rel` é o caminho relativo POSIX dentro do pacote (o stem não é único entre runtimes).
    """
    raw = json.loads((SAMPLES_DIR / rel).read_text(encoding="utf-8"))
    spec = raw.get("metadata", {}).get("kernelspec", {})
    return spec if isinstance(spec, dict) else {}


def _present_in_root(store: NotebookStore, rel: str) -> bool:
    """True se `rel` é arquivo regular dentro da raiz; symlink que escapa dela conta como ausente."""
    try:
        return store.resolve(rel).is_file()
    except (StoreError, OSError):
        return False


def _describe(name: str, rel: str) -> dict[str, str]:
    spec = _kernelspec(rel)
    kernel_name = str(spec.get("name", ""))
    # O kernelspec do .ipynb não traz a chave de registro do DuckDB (ela vive no kernelspec instalado);
    # o nome fixo basta para classificar o exemplo.
    metadata = {DUCKDB_METADATA_KEY: {}} if kernel_name == DUCKDB_KERNEL_NAME else {}
    return {
        "name": name,
        "path": rel,
        "kernel_name": kernel_name,
        "runtime_kind": runtime_kind(kernel_name, metadata),
        "display_name": str(spec.get("display_name", "")),
    }


@router.get("")
def list_samples(request: Request) -> list[dict[str, str]]:
    """Lista apenas os exemplos em destaque (`FEATURED_SAMPLES`) presentes na raiz, na ordem da constante.

    O exemplo é identificado SOMENTE pelo caminho (subpasta + arquivo), nunca pelo conteúdo: executar
    e salvar um exemplo grava saídas no .ipynb, e uma comparação por hash deixaria de reconhecê-lo.
    Consequência: um notebook do usuário no mesmo caminho de um exemplo é tratado como exemplo.
    Destaque ausente da raiz do usuário ou do pacote é omitido.
    """
    store: NotebookStore = request.app.state.store
    return [
        _describe(PurePosixPath(rel).stem, rel)
        for rel in FEATURED_SAMPLES
        if (SAMPLES_DIR / rel).is_file() and _present_in_root(store, rel)
    ]
