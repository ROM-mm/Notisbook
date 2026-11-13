"""Primeira execução: define a pasta padrão de notebooks e copia os exemplos do pacote.

Roda na partida, depois de `ensure_home` e antes de ler as preferências. A primeira execução é
`preferences.json` ausente; o marcador `samples_seeded` impede recriar exemplos apagados pelo usuário.
"""

import os
import sys
import tempfile
from pathlib import Path

from .config import default_root
from .preferences import (
    RootRejected,
    mark_samples_seeded,
    preferences_path,
    validate_notebooks_root,
    write_notebooks_root,
)

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
NOTEBOOK_SUFFIX = ".ipynb"
# Igual ao de um notebook criado pelo app (`NotebookStore.create` grava via `mkstemp`).
NOTEBOOK_MODE = 0o600


def _has_notebook(folder: Path) -> bool:
    """True se a árvore tem ao menos um `.ipynb` visível; ignora pastas ocultas e para no primeiro achado."""
    for _, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if any(f.endswith(NOTEBOOK_SUFFIX) and not f.startswith(".") for f in files):
            return True
    return False


def _publish_sample(sample: Path, target: Path) -> None:
    """Copia `sample` para `target` sem sobrescrever: temporário oculto na mesma pasta + `os.link`.

    O link falha com FileExistsError se o destino já existe (exemplo editado), e o destino nunca
    aparece truncado. O temporário é sempre removido.
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".seed-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(sample.read_bytes())
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, NOTEBOOK_MODE)
        try:
            os.link(tmp_name, target)
        except FileExistsError:
            pass
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def _seed_samples(home: Path) -> None:
    """Copia os exemplos para `<home>/notebooks` e grava o marcador. Levanta OSError em falha (sem marcador)."""
    samples = sorted(SAMPLES_DIR.glob(f"*{NOTEBOOK_SUFFIX}"))
    if not samples:
        raise FileNotFoundError(f"no bundled samples in {SAMPLES_DIR}")
    folder = default_root(home)
    folder.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        _publish_sample(sample, folder / sample.name)
    mark_samples_seeded(home)


def _adopt_legacy_root(home: Path) -> bool:
    """Adota `~/notebooks` quando tem notebooks e passa na validação; só vale com a pasta de dados padrão."""
    if os.environ.get("NOTISBOOK_HOME"):
        return False
    legacy = Path.home() / "notebooks"
    if not _has_notebook(legacy):
        return False
    try:
        resolved = validate_notebooks_root(str(legacy), home)
    except RootRejected:
        return False
    write_notebooks_root(home, resolved, samples_seeded=True)
    return True


def run_onboarding(home: Path, cli_root: Path | None) -> None:
    """No-op com `--root` ou `preferences.json` existente; senão adota `~/notebooks` ou semeia os exemplos.

    Qualquer falha vira aviso no stderr, sem marcador (a próxima partida tenta de novo); o app sobe.
    """
    if cli_root is not None or os.path.lexists(preferences_path(home)):
        return
    try:
        if not _adopt_legacy_root(home):
            _seed_samples(home)
    except OSError as exc:
        print(f"Notisbook: could not set up the default notebooks folder: {exc.strerror or exc}", file=sys.stderr)
