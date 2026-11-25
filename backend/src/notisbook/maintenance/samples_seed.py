"""`notisbook --seed-samples [--if-missing]`: copia os exemplos que faltam para a pasta de notebooks ativa e termina.

Destino = `notebooks_root` salvo e utilizável, senão `<home>/notebooks` (mesma resolução do app). Sem
`preferences.json` decide como o onboarding: adota `~/notebooks` (sem copiar) ou semeia a pasta padrão.
Nunca sobrescreve. Com `--if-missing`, pasta existente (mesmo vazia) não recebe nada, e nada é criado antes
dessa checagem. Não sobe app nem NotebookStore; sem lock.
Exit: 0 copiou, nada a copiar, adotou legado ou pulou; 1 falha de cópia ou do marcador; 2 home impossível; 130 Ctrl+C.
"""

import os
import sys

from ..config import default_home
from ..onboarding import adopt_legacy_root, saved_or_default_root, seed_samples_into
from ..preferences import mark_samples_seeded, preferences_path


def run(*, if_missing: bool = False) -> int:
    """Semeia os exemplos; devolve o exit code (ver o docstring do módulo)."""
    home = default_home()
    try:
        has_preferences = os.path.lexists(preferences_path(home))
        folder, _ = saved_or_default_root(home)
        if if_missing and os.path.lexists(folder):
            print(f"Notisbook: notebooks folder {folder} already exists; no samples copied.")
            return 0
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"Notisbook: cannot prepare the data folder {home} ({exc.strerror or exc}).", file=sys.stderr)
            return 2
        try:
            if not has_preferences and adopt_legacy_root(home):
                print("Notisbook: existing notebooks in ~/notebooks adopted as the notebooks folder; no samples copied.")
                return 0
            copied, existing = seed_samples_into(folder)
            mark_samples_seeded(home)
        except OSError as exc:
            print(f"Notisbook: could not copy the sample notebooks to {folder} ({exc.strerror or exc}).", file=sys.stderr)
            return 1
        print(f"Notisbook: {copied} sample notebook(s) copied to {folder} ({existing} already there).")
        return 0
    except KeyboardInterrupt:
        print("Notisbook: interrupted; the sample notebooks may not be fully copied.", file=sys.stderr)
        return 130
