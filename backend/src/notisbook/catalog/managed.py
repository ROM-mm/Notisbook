"""Salvaguarda de pastas MANAGED, fonte única para o backend e para o hook do kernel."""

import os
import shutil


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


def delete_managed_table(path, root):
    """Apaga a pasta de uma tabela MANAGED após `managed_table_dir`; devolve um texto de erro ou None.

    Só o backend usa (o hook tem a própria cópia, injetada no kernel). Pasta já ausente não é erro.
    """
    real, error = managed_table_dir(path, root)
    if error:
        return error
    if not os.path.isdir(real):
        return None
    try:
        shutil.rmtree(real)
    except OSError as exc:
        return exc.strerror or "could not remove the folder"
    return None
