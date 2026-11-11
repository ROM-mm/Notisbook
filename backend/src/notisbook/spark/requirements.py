"""Validação de nome (PEP 508) e especificador (PEP 440) de libs pedidas pelo usuário.

A entrada nunca define a origem do pacote: URL, caminho, extras e marcadores são recusados,
e a string entregue ao `uv` é reconstruída a partir dos objetos já parseados.
"""

import re

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name

from .bundles import bundle_for

MAX_NAME = 100
MAX_SPEC = 200
_NAME = re.compile(r"([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])", re.IGNORECASE)
_BASE_CORE = ("pyspark", "py4j", "ipykernel", "duckdb")
_FORBIDDEN_SPEC = ("===", "@", ";", "[")
_PIN_NAME = re.compile(r"[A-Za-z0-9._-]+")


def validate_name(name: str) -> str:
    """Nome canônico; levanta ValueError se não for um nome de distribuição PEP 508."""
    if not name or len(name) > MAX_NAME or _NAME.fullmatch(name) is None:
        raise ValueError(f"invalid library name: {name[:MAX_NAME]!r}")
    return str(canonicalize_name(name))


def parse_requirement(name: str, spec: str) -> str:
    """`<nome-canônico><spec normalizada>`; levanta ValueError para qualquer entrada insegura."""
    canonical = validate_name(name)
    spec = spec.strip() if spec else ""
    if not spec:
        return canonical
    if len(spec) > MAX_SPEC or any(token in spec for token in _FORBIDDEN_SPEC) or any(c.isspace() for c in spec):
        raise ValueError(f"invalid version specifier for {canonical}")
    try:
        parsed = SpecifierSet(spec)
    except InvalidSpecifier as exc:
        raise ValueError(f"invalid version specifier for {canonical}") from exc
    return f"{canonical}{parsed}"


def core_names(version: str) -> set[str]:
    """Nomes canônicos das libs base do ambiente: pyspark, py4j, ipykernel, duckdb e o pip do bundle."""
    names = set(_BASE_CORE)
    bundle = bundle_for(version)
    for pin in bundle.pip if bundle else ():
        match = _PIN_NAME.match(pin)
        if match:
            names.add(str(canonicalize_name(match.group(0))))
    return names
