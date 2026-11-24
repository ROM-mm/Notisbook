"""Exemplos empacotados que ainda existem na raiz de notebooks atual."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..kernels.service import DUCKDB_KERNEL_NAME, DUCKDB_METADATA_KEY, runtime_kind
from ..notebooks.store import NotebookStore, StoreError
from ..onboarding import SAMPLES_DIR, bundled_samples
from ..security import require_token, require_trusted_host

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
    """Lista os exemplos empacotados presentes na raiz, ordenados pelo caminho relativo.

    O exemplo é identificado SOMENTE pelo caminho (subpasta + arquivo), nunca pelo conteúdo: executar
    e salvar um exemplo grava saídas no .ipynb, e uma comparação por hash deixaria de reconhecê-lo.
    Consequência: um notebook do usuário no mesmo caminho de um exemplo é tratado como exemplo.
    """
    store: NotebookStore = request.app.state.store
    rels = [(rel.stem, rel.as_posix()) for rel in bundled_samples()]
    return [_describe(name, path) for name, path in rels if _present_in_root(store, path)]
