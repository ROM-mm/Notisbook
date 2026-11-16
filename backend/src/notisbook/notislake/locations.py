"""Locations `s3a://notislake/...`: camadas, forma MANAGED, regra de destino e sobreposição.

Módulo autocontido (só stdlib) para ser importado por catálogo, REST e hook sem ciclos. Não
consulta rede nem disco: toda decisão é sintática e a sobreposição recebe as locations já
conhecidas como argumento. O schema decide a camada (D1): a tabela MANAGED fica em
`s3a://notislake/<camada>/<tabela>`, sem `spark`/`iceberg` nem `.db` no caminho. Os erros são
`InvalidLocation` com `code` categórico; a mensagem nunca repete a entrada.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

BUCKET = "notislake"
SCHEME = "s3a"
LAYERS = ("landing", "bronze", "silver", "gold")
MIN_DEPTH = 2  # `<camada>/<dataset>`: a raiz do bucket e uma camada sozinha não são locations de tabela
ROOT_URI = f"{SCHEME}://{BUCKET}"  # raiz do bucket: warehouse do Iceberg, que cria `<ns>/<t>` abaixo dela

_PREFIX = f"{SCHEME}://{BUCKET}/"
_ALIAS_SCHEMES = ("s3", "s3a", "s3n")


class InvalidLocation(ValueError):
    """Destino fora do contrato; `code` é categórico e a mensagem não repete a entrada."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NotislakeLocation:
    """Location normalizada: `segments` (>= 2) são os componentes após o bucket, sem `/` final."""

    segments: tuple[str, ...]

    @property
    def key(self) -> str:
        """Chave do objeto/prefixo no bucket, sem `/` final."""
        return "/".join(self.segments)

    @property
    def uri(self) -> str:
        return _PREFIX + self.key


def _split(uri: str) -> tuple[str, ...]:
    """Segmentos após o bucket, de profundidade >= 1; `not_notislake`, `too_shallow` ou `bad_segment`."""
    if not isinstance(uri, str) or not uri.startswith(_PREFIX):
        raise InvalidLocation("not_notislake")
    rest = uri[len(_PREFIX) :].removesuffix("/")
    if not rest:
        raise InvalidLocation("too_shallow")
    segments = tuple(rest.split("/"))
    if any(part in ("", ".", "..") for part in segments):
        raise InvalidLocation("bad_segment")
    return segments


def parse_notislake(uri: str) -> NotislakeLocation:
    """Aceita só `s3a://notislake/<a>/<b>[/...]`; levanta `InvalidLocation` (código em `.code`).

    Códigos: `not_notislake` (esquema ou bucket diferente), `too_shallow` (raiz ou profundidade 1),
    `bad_segment` (`.`, `..` ou vazio, inclusive `//`). Uma `/` final é tolerada e descartada.
    """
    segments = _split(uri)
    if len(segments) < MIN_DEPTH:
        raise InvalidLocation("too_shallow")
    return NotislakeLocation(segments)


def targets_notislake(uri: str) -> bool:
    """`uri` usa `s3`, `s3a` ou `s3n` e aponta para o bucket `notislake` (ou para dentro dele)."""
    if not isinstance(uri, str):
        return False
    scheme, sep, rest = uri.partition("://")
    return bool(sep) and scheme.lower() in _ALIAS_SCHEMES and rest.partition("/")[0] == BUCKET


def layer_of_schema(schema: str) -> str | None:
    """Camada que o schema nomeia (comparação sem caixa) ou `None` se não for uma das `LAYERS`."""
    name = schema.strip().lower() if isinstance(schema, str) else ""
    return name if name in LAYERS else None


def layer_uri(layer: str) -> str:
    """`s3a://notislake/<camada>`; `InvalidLocation("not_a_layer")` se `layer` não for uma camada."""
    if layer not in LAYERS:
        raise InvalidLocation("not_a_layer")
    return f"{_PREFIX}{layer}"


def layer_of_location(uri: str) -> str | None:
    """Camada em que `uri` (válida, qualquer profundidade >= 1) está; `None` se inválida ou fora delas."""
    try:
        first = _split(uri)[0]
    except InvalidLocation:
        return None
    return first if first in LAYERS else None


def managed_location(schema: str, table: str) -> str:
    """Forma MANAGED `s3a://notislake/<camada>/<tabela>` (D1).

    Levanta `InvalidLocation`: `schema_not_layer` (D3) ou `bad_segment` (nome vazio, `.`, `..`,
    com `/`, `\\` ou caractere de controle). O nome da tabela entra no caminho como veio.
    """
    layer = layer_of_schema(schema)
    if layer is None:
        raise InvalidLocation("schema_not_layer")
    if (
        not isinstance(table, str)
        or table in ("", ".", "..")
        or any(ch in "/\\" or ord(ch) < 32 for ch in table)
    ):
        raise InvalidLocation("bad_segment")
    return f"{_PREFIX}{layer}/{table}"


def managed_table(uri: str) -> bool:
    """`uri` tem exatamente a forma `s3a://notislake/<camada>/<tabela>` (caixa exata)."""
    try:
        segments = parse_notislake(uri).segments
    except InvalidLocation:
        return False
    return len(segments) == MIN_DEPTH and segments[0] in LAYERS


def within(child: str, parent: str) -> bool:
    """`child` é igual a `parent` ou está dentro dele; ambos precisam ser locations válidas."""
    try:
        c = parse_notislake(child).segments
        p = parse_notislake(parent).segments
    except InvalidLocation:
        return False
    return c[: len(p)] == p


def overlaps(a: str, b: str) -> bool:
    """`a` e `b` são iguais, um está dentro do outro (por segmento) ou são locations inválidas -> False."""
    return within(a, b) or within(b, a)


def _overlaps_any(location: str, known: Iterable[str], skip: str | None = None) -> bool:
    """Alguma location conhecida (válida, diferente de `skip`) sobrepõe `location`."""
    own = _normalized(skip) if skip is not None else None
    for other in known:
        norm = _normalized(other)
        if norm is not None and norm != own and overlaps(location, norm):
            return True
    return False


def _normalized(uri: str) -> str | None:
    """`uri` sem `/` final se for location válida de tabela; senão `None`."""
    try:
        return parse_notislake(uri).uri
    except InvalidLocation:
        return None


def table_destination(
    schema: str,
    table: str,
    location: str | None,
    known_locations: Iterable[str],
    own_location: str | None = None,
) -> str:
    """Location efetiva de `schema.table` no notislake: MANAGED se `location` é `None`, senão a externa.

    D3: schema fora das camadas é recusado. D4: externa precisa estar na camada do schema. D2/D4:
    não pode sobrepor outra tabela de `known_locations` (`own_location`, a própria, é ignorada).
    Códigos: `schema_not_layer`, `not_notislake`, `too_shallow`, `bad_segment`, `outside_layer`,
    `overlaps_table`.
    """
    layer = layer_of_schema(schema)
    if layer is None:
        raise InvalidLocation("schema_not_layer")
    if location is None:
        effective = managed_location(schema, table)
    else:
        effective = parse_notislake(location).uri
        if layer_of_location(effective) != layer:
            raise InvalidLocation("outside_layer")
    if _overlaps_any(effective, known_locations, own_location):
        raise InvalidLocation("overlaps_table")
    return effective


def check_path_write(
    location: str,
    known_locations: Iterable[str],
    own_location: str | None = None,
) -> str:
    """Valida escrita por path sem tabela no notislake (D8) e devolve a location normalizada.

    Exige profundidade >= 2 (`too_shallow`), dentro de uma camada (`outside_layer`) e sem sobrepor
    tabela conhecida (`overlaps_table`). Exceção: `location` igual à pasta de `own_location` (a
    própria tabela) é permitida; subpasta ou pasta-mãe dela continua recusada.
    """
    effective = parse_notislake(location).uri
    if layer_of_location(effective) is None:
        raise InvalidLocation("outside_layer")
    if own_location is not None and _normalized(own_location) == effective:
        return effective
    if _overlaps_any(effective, known_locations):
        raise InvalidLocation("overlaps_table")
    return effective
