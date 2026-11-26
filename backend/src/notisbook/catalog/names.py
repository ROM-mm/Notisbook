"""Regra de nome de schema e de tabela compartilhada por `schemas` e `glue_repo`, sem dependência de nenhum dos dois."""

import re

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
