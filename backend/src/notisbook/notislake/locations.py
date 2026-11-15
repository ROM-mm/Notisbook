"""Locations `s3a://notislake/...`: análise estrita, contenção e prefixo reservado do Iceberg.

Módulo autocontido (só stdlib) para ser importado por catálogo, REST e hook sem ciclos. Não
consulta rede nem disco; a decisão de aceitar ou recusar uma location é só sintática.
"""

from __future__ import annotations

from dataclasses import dataclass

BUCKET = "notislake"
SCHEME = "s3a"
MIN_DEPTH = 2  # `<camada>/<dataset>`: a raiz do bucket e uma camada sozinha não são locations de tabela
RESERVED_ICEBERG_PREFIX = f"{SCHEME}://{BUCKET}/bronze/iceberg/"

_PREFIX = f"{SCHEME}://{BUCKET}/"


class InvalidLocation(ValueError):
    """Location fora do contrato; `code` é categórico e a mensagem não repete a entrada."""

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


def parse_notislake(uri: str) -> NotislakeLocation:
    """Aceita só `s3a://notislake/<a>/<b>[/...]`; levanta `InvalidLocation` (código em `.code`).

    Códigos: `not_notislake` (esquema ou bucket diferente), `too_shallow` (raiz ou profundidade 1),
    `bad_segment` (`.`, `..` ou vazio, inclusive `//`). Uma `/` final é tolerada e descartada.
    """
    if not isinstance(uri, str) or not uri.startswith(_PREFIX):
        raise InvalidLocation("not_notislake")
    rest = uri[len(_PREFIX) :].removesuffix("/")
    if not rest:
        raise InvalidLocation("too_shallow")
    segments = tuple(rest.split("/"))
    if any(part in ("", ".", "..") for part in segments):
        raise InvalidLocation("bad_segment")
    if len(segments) < MIN_DEPTH:
        raise InvalidLocation("too_shallow")
    return NotislakeLocation(segments)


def within(child: str, parent: str) -> bool:
    """`child` é igual a `parent` ou está dentro dele; ambos precisam ser locations válidas."""
    try:
        c = parse_notislake(child).segments
        p = parse_notislake(parent).segments
    except InvalidLocation:
        return False
    return c[: len(p)] == p


def is_reserved_iceberg(uri: str) -> bool:
    """`uri` é válida e é `s3a://notislake/bronze/iceberg` ou está abaixo dele."""
    try:
        loc = parse_notislake(uri)
    except InvalidLocation:
        return False
    return (loc.uri + "/").startswith(RESERVED_ICEBERG_PREFIX)
