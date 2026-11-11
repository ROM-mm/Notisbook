"""Salvaguardas de exclusão de pastas, compartilhadas pelos painéis Notebooks e Files."""

import shutil
from collections.abc import Iterable
from pathlib import Path


class PartialDelete(Exception):
    """A remoção recursiva falhou no meio; parte da árvore já foi apagada."""


def _parts(path: Path, fold: bool) -> tuple[str, ...]:
    return tuple(p.casefold() for p in path.parts) if fold else path.parts


def is_within(inner: Path, outer: Path, *, fold: bool = False) -> bool:
    """True quando `inner` é `outer` ou está dentro dele. `fold` ignora caixa (APFS), só para recusar mais."""
    o = _parts(outer, fold)
    return _parts(inner, fold)[: len(o)] == o


def is_protected(real: Path, protected: Iterable[Path], *, fold: bool = False) -> bool:
    """True quando `real` é um caminho protegido ou um ancestral dele (apagá-lo levaria o protegido junto)."""
    return any(is_within(p, real, fold=fold) for p in protected)


def remove_tree(target: Path) -> None:
    """Remove a pasta recursivamente; levanta `PartialDelete` (sem o caminho absoluto) se algo falhar."""
    try:
        shutil.rmtree(target)
    except OSError as exc:
        # Só o rmtree deixa estado parcial; a mensagem não expõe o caminho absoluto.
        raise PartialDelete(f"Partially deleted: {exc.strerror or 'could not remove all items'}") from exc
