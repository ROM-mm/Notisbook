"""Locations S3 do MinIO: bucket gerenciado reservado, regra única de destino das tabelas e sobreposição.

Módulo autocontido (só stdlib) para ser importado por catálogo, REST e hook sem ciclos; o hook o recebe como
texto. Não consulta rede nem disco: toda decisão é sintática e a sobreposição recebe as locations já conhecidas
como argumento. `s3://` é sinônimo de `s3a://` só na entrada; a forma interna é sempre `s3a`.

Gerenciada (sem LOCATION) fica em `s3a://notisbook-managed/<schema>/<tabela>`, bucket reservado do app. Externa
(com LOCATION) fica em qualquer outro bucket, com a sobreposição checada sem distinção de caixa. O schema não
define camada. Os erros são `InvalidLocation` com `code` categórico; a mensagem nunca repete a entrada.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

BUCKET = "notislake"
MANAGED_BUCKET = "notisbook-managed"
SCHEME = "s3a"
MANAGED_ROOT = f"{SCHEME}://{MANAGED_BUCKET}"
MIN_DEPTH = 1  # `<pasta>`: a raiz do bucket sozinha não é location de tabela

# Buckets acessíveis no escopo manual (o automático só valida o nome, `valid_bucket_name`).
KNOWN_BUCKETS = (BUCKET, MANAGED_BUCKET)

_ALIAS_SCHEMES = ("s3", "s3a", "s3n")

_BUCKET_MIN_LEN = 3
_BUCKET_MAX_LEN = 63
_BUCKET_CHARS = re.compile(r"[a-z0-9][a-z0-9.-]*[a-z0-9]")
_IPV4_LIKE = re.compile(r"\d{1,3}(\.\d{1,3}){3}")
_BUCKET_RESERVED_PREFIXES = ("xn--", "sthree-", "amzn-s3-demo-")
_BUCKET_RESERVED_SUFFIXES = ("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3")


class InvalidLocation(ValueError):
    """Destino fora do contrato; `code` é categórico e a mensagem não repete a entrada."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Location:
    """Location normalizada: `bucket` e `segments` (>= 1) após ele, sem `/` final."""

    bucket: str
    segments: tuple[str, ...]

    @property
    def key(self) -> str:
        """Chave do objeto/prefixo no bucket, sem `/` final."""
        return "/".join(self.segments)

    @property
    def uri(self) -> str:
        return f"{SCHEME}://{self.bucket}/{self.key}"


def canonical(uri: str) -> str:
    """`s3://` vira `s3a://` (forma interna); qualquer outra entrada, inclusive `s3n://`, volta como veio."""
    if isinstance(uri, str):
        scheme, sep, rest = uri.partition("://")
        if sep and scheme.lower() == "s3":
            return f"{SCHEME}://{rest}"
    return uri


def valid_bucket_name(name: str) -> bool:
    """Nome de bucket pelas regras de nomenclatura do S3 (fonte única; backend e hook usam esta função).

    3 a 63 caracteres `[a-z0-9.-]`, começando e terminando em letra ou dígito, sem `..`, sem formato de
    endereço IPv4 e sem os prefixos/sufixos que a AWS reserva.
    """
    if not isinstance(name, str) or not _BUCKET_MIN_LEN <= len(name) <= _BUCKET_MAX_LEN:
        return False
    return (
        _BUCKET_CHARS.fullmatch(name) is not None
        and ".." not in name
        and _IPV4_LIKE.fullmatch(name) is None
        and not name.startswith(_BUCKET_RESERVED_PREFIXES)
        and not name.endswith(_BUCKET_RESERVED_SUFFIXES)
    )


def parse_location(uri: str) -> Location:
    """Aceita `s3a://<bucket>/<a>[/...]` (ou `s3://`); levanta `InvalidLocation` (código em `.code`).

    Códigos: `not_s3` (esquema diferente de s3/s3a, `s3n` inclusive), `bad_bucket` (nome inválido), `too_shallow`
    (raiz do bucket), `bad_segment` (`.`, `..` ou vazio, inclusive `//`). Uma `/` final é tolerada e descartada.
    """
    uri = canonical(uri)
    prefix = f"{SCHEME}://"
    if not isinstance(uri, str) or not uri.startswith(prefix):
        raise InvalidLocation("not_s3")
    bucket, _, rest = uri[len(prefix) :].partition("/")
    if not valid_bucket_name(bucket):
        raise InvalidLocation("bad_bucket")
    rest = rest.removesuffix("/")
    if not rest:
        raise InvalidLocation("too_shallow")
    segments = tuple(rest.split("/"))
    if any(part in ("", ".", "..") for part in segments):
        raise InvalidLocation("bad_segment")
    return Location(bucket, segments)


def bucket_of(uri: str) -> str | None:
    """Bucket de uma URI `s3`/`s3a`/`s3n` (qualquer nome, sem validar); `None` para outro esquema ou entrada."""
    if not isinstance(uri, str):
        return None
    scheme, sep, rest = uri.partition("://")
    if not sep or scheme.lower() not in _ALIAS_SCHEMES:
        return None
    return rest.partition("/")[0]


def targets_managed(uri: str) -> bool:
    """`uri` usa `s3`, `s3a` ou `s3n` e aponta para o bucket reservado (ou para dentro dele)."""
    return bucket_of(uri) == MANAGED_BUCKET


def known_buckets() -> tuple[str, ...]:
    """Buckets que leitura e escrita alcançam no escopo manual."""
    return KNOWN_BUCKETS


def unknown_bucket(uri: str) -> str | None:
    """Bucket de uma URI `s3`/`s3a`/`s3n` que não está em `KNOWN_BUCKETS` (comparação exata); senão `None`."""
    bucket = bucket_of(uri)
    return None if bucket is None or bucket in KNOWN_BUCKETS else bucket


def _plain_segment(part: str) -> bool:
    """Nome que entra no caminho como veio: não vazio, sem `.`/`..`, `/`, `\\` nem caractere de controle."""
    return isinstance(part, str) and part not in ("", ".", "..") and not any(ch in "/\\" or ord(ch) < 32 for ch in part)


def schema_location(schema: str, scheme: str = SCHEME) -> str:
    """Location do schema no bucket reservado, `<scheme>://notisbook-managed/<schema>`; `bad_segment` se o nome não serve."""
    if not _plain_segment(schema):
        raise InvalidLocation("bad_segment")
    return f"{scheme}://{MANAGED_BUCKET}/{schema}"


def schema_location_matches(schema: str, location: str) -> bool:
    """`location` é a do schema no bucket reservado (`s3`/`s3a`, `/` final tolerada, caixa exata como em `managed_location`)."""
    try:
        parsed = parse_location(location)
    except InvalidLocation:
        return False
    return parsed.bucket == MANAGED_BUCKET and len(parsed.segments) == 1 and parsed.segments[0] == schema


def managed_location(schema: str, table: str) -> str:
    """Forma gerenciada `s3a://notisbook-managed/<schema>/<tabela>`; `bad_segment` se algum nome não serve.

    Os nomes entram no caminho como vieram.
    """
    if not _plain_segment(schema) or not _plain_segment(table):
        raise InvalidLocation("bad_segment")
    return f"{MANAGED_ROOT}/{schema}/{table}"


def managed_table(uri: str) -> bool:
    """`uri` tem exatamente a forma `s3a://notisbook-managed/<schema>/<tabela>` (caixa exata)."""
    try:
        parsed = parse_location(uri)
    except InvalidLocation:
        return False
    return parsed.bucket == MANAGED_BUCKET and len(parsed.segments) == 2


def _folded(location: Location) -> tuple[str, tuple[str, ...]]:
    """Bucket e segmentos sem caixa: o MinIO roda em disco que não distingue `Silver` de `silver`."""
    return location.bucket, tuple(part.casefold() for part in location.segments)


def within(child: str, parent: str) -> bool:
    """`child` é igual a `parent` ou está dentro dele (sem distinção de caixa); ambos precisam ser locations válidas."""
    try:
        c_bucket, c = _folded(parse_location(child))
        p_bucket, p = _folded(parse_location(parent))
    except InvalidLocation:
        return False
    return c_bucket == p_bucket and c[: len(p)] == p


def overlaps(a: str, b: str) -> bool:
    """`a` e `b` são iguais, um está dentro do outro (por segmento) ou são locations inválidas -> False."""
    return within(a, b) or within(b, a)


def _normalized(uri: str) -> str | None:
    """`uri` sem `/` final se for location válida; senão `None`."""
    try:
        return parse_location(uri).uri
    except InvalidLocation:
        return None


def _overlaps_any(location: str, known: Iterable[str], skip: str | None = None) -> bool:
    """Alguma location conhecida (válida, diferente de `skip`) sobrepõe `location`."""
    own = _normalized(skip) if skip is not None else None
    for other in known:
        norm = _normalized(other)
        if norm is not None and norm != own and overlaps(location, norm):
            return True
    return False


def table_destination(
    schema: str,
    table: str,
    location: str | None,
    known_locations: Iterable[str],
    own_location: str | None = None,
    pending: Iterable[str] = (),
) -> str:
    """Location efetiva de `schema.table`: gerenciada se `location` é `None`, senão a externa, em qualquer bucket.

    No bucket reservado só vale a forma gerenciada da própria tabela; outra pasta dele é recusada. A externa não
    pode sobrepor outra tabela de `known_locations` (`own_location`, a própria, é ignorada) e nenhuma destas
    pode cair numa pasta com exclusão pendente em `pending`.
    Códigos: `not_s3`, `bad_bucket`, `too_shallow`, `bad_segment`, `reserved_bucket`, `overlaps_table`, `pending_cleanup`.
    """
    managed = managed_location(schema, table)
    if location is None:
        effective = managed
    else:
        effective = parse_location(location).uri
        if targets_managed(effective) and effective != managed:
            raise InvalidLocation("reserved_bucket")
    if _overlaps_any(effective, known_locations, own_location):
        raise InvalidLocation("overlaps_table")
    if _overlaps_any(effective, pending):
        raise InvalidLocation("pending_cleanup")
    return effective


def check_path_write(
    location: str,
    known_locations: Iterable[str],
    own_location: str | None = None,
) -> str:
    """Valida escrita por path sem tabela e devolve a location normalizada.

    Recusa a raiz do bucket (`too_shallow`), o bucket reservado (`reserved_bucket`) e o que sobrepõe tabela conhecida
    (`overlaps_table`). Exceção: `location` igual à pasta de `own_location` (a própria tabela) é permitida;
    subpasta ou pasta-mãe dela continua recusada.
    """
    effective = parse_location(location).uri
    if own_location is not None and _normalized(own_location) == effective:
        return effective
    if targets_managed(effective):
        raise InvalidLocation("reserved_bucket")
    if _overlaps_any(effective, known_locations):
        raise InvalidLocation("overlaps_table")
    return effective
