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
    read_notebooks_root,
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


def bundled_samples() -> list[Path]:
    """Caminhos relativos a `SAMPLES_DIR` de todos os exemplos, em ordem estável; ignora pastas ocultas."""
    found = (p.relative_to(SAMPLES_DIR) for p in SAMPLES_DIR.rglob(f"*{NOTEBOOK_SUFFIX}") if p.is_file())
    return sorted(rel for rel in found if not any(part.startswith(".") for part in rel.parts))


def _seed_samples(home: Path) -> None:
    """Copia os exemplos para `<home>/notebooks` e grava o marcador. Levanta OSError em falha (sem marcador)."""
    samples = bundled_samples()
    if not samples:
        raise FileNotFoundError(f"no bundled samples in {SAMPLES_DIR}")
    folder = default_root(home)
    folder.mkdir(parents=True, exist_ok=True)
    for rel in samples:
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        _publish_sample(SAMPLES_DIR / rel, target)
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


def adopt_legacy_root(home: Path) -> bool:
    """Mesma adoção de `~/notebooks` do onboarding (grava `preferences.json`); True se adotou. Levanta OSError ao gravar."""
    return _adopt_legacy_root(home)


def saved_or_default_root(home: Path) -> tuple[Path, str]:
    """Pasta de notebooks e sua origem (`"saved"` ou `"default"`), sem criar nada.

    Usa o `notebooks_root` salvo quando passa na validação da API (precisa existir); senão avisa no stderr
    e cai em `default_root(home)`. Fonte única para o app e para `--seed-samples`.
    """
    saved = read_notebooks_root(home)
    if saved is not None:
        try:
            return validate_notebooks_root(saved, home), "saved"
        except RootRejected as exc:
            print(f"Notisbook: saved notebooks folder {saved} is not usable ({exc.message}); using the default.", file=sys.stderr)
    return default_root(home).resolve(), "default"


def seed_samples_into(folder: Path) -> tuple[int, int]:
    """Cria `folder` se faltar e copia os exemplos que ainda não existem nele; devolve (copiados, já existentes).

    Nunca sobrescreve (`lexists` cobre também link simbólico). Não grava o marcador `samples_seeded`.
    Levanta OSError em falha, inclusive FileNotFoundError se o pacote não traz exemplos.
    """
    samples = bundled_samples()
    if not samples:
        raise FileNotFoundError(f"no bundled samples in {SAMPLES_DIR}")
    folder.mkdir(parents=True, exist_ok=True)
    copied = existing = 0
    for rel in samples:
        target = folder / rel
        if os.path.lexists(target):
            existing += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _publish_sample(SAMPLES_DIR / rel, target)
        copied += 1
    return copied, existing


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
