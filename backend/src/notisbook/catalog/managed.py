"""Salvaguarda de pastas MANAGED, fonte única para o backend e para o hook do kernel."""

import os


def managed_table_dir(path, root):
    """Valida a pasta de uma tabela MANAGED sob `root`; devolve `(real, erro)`.

    Autocontida (só `os`): o hook do kernel recebe este mesmo código-fonte por `inspect.getsource`.
    Aceita `<root>/<t>` ou `<root>/<db>.db/<t>`; recusa a raiz, pastas `*.db` e o que está fora de `root`
    (comparação por realpath). `real` é None quando há erro.
    """
    real, base = os.path.realpath(path), os.path.realpath(root)
    if not real.startswith(base + os.sep):
        return None, "outside the managed warehouse"
    parts = os.path.relpath(real, base).split(os.sep)
    if len(parts) > 2 or (len(parts) == 2 and not parts[0].endswith(".db")) or parts[-1].endswith(".db"):
        return None, "not a table folder of the managed warehouse"
    return real, None
