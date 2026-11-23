"""Exemplos empacotados que ainda existem na raiz de notebooks atual."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..kernels.service import DUCKDB_KERNEL_NAME, DUCKDB_METADATA_KEY, runtime_kind
from ..notebooks.store import NOTEBOOK_SUFFIX, NotebookStore, StoreError
from ..onboarding import SAMPLES_DIR
from ..security import require_token, require_trusted_host

router = APIRouter(
    prefix="/api/samples",
    dependencies=[Depends(require_token), Depends(require_trusted_host)],
)


def _kernelspec(sample_name: str) -> dict[str, Any]:
    """`metadata.kernelspec` do exemplo empacotado (fonte da verdade), nunca da cópia do usuário."""
    raw = json.loads((SAMPLES_DIR / f"{sample_name}{NOTEBOOK_SUFFIX}").read_text(encoding="utf-8"))
    spec = raw.get("metadata", {}).get("kernelspec", {})
    return spec if isinstance(spec, dict) else {}


def _present_in_root(store: NotebookStore, rel: str) -> bool:
    """True se `rel` é arquivo regular dentro da raiz; symlink que escapa dela conta como ausente."""
    try:
        return store.resolve(rel).is_file()
    except (StoreError, OSError):
        return False


def _describe(name: str, rel: str) -> dict[str, str]:
    spec = _kernelspec(name)
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
    store: NotebookStore = request.app.state.store
    names = sorted(p.stem for p in SAMPLES_DIR.glob(f"*{NOTEBOOK_SUFFIX}"))
    return [_describe(n, f"{n}{NOTEBOOK_SUFFIX}") for n in names if _present_in_root(store, f"{n}{NOTEBOOK_SUFFIX}")]
