"""Verificação de assinatura AWS Signature V4 (serviço `glue`) das requisições do endpoint Glue.

Só calcula: quem decide a credencial (id da sessão como access key, token de runtime como secret) é o chamador.
`parse_authorization` valida o cabeçalho `Authorization`; `canonical_request` e `signature_for` refazem a assinatura
com o segredo da sessão. O chamador compara com `hmac.compare_digest`. Nada aqui registra segredo ou assinatura.
A região é a do escopo recebido (qualquer valor bem formado). `X-Amz-Date` precisa estar a até 24 h do relógio do
backend: a janela larga tolera o desvio do relógio da VM do container, e o segredo da sessão já limita quem assina.
O corpo sempre entra na assinatura pelo SHA-256 (`UNSIGNED-PAYLOAD` é recusado).
"""

import hashlib
import hmac
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, quote

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "glue"
REQUIRED_SIGNED_HEADERS = frozenset({"host", "x-amz-date", "x-amz-target"})

_AMZ_DATE_RE = re.compile(r"\d{8}T\d{6}Z")
_DATE_RE = re.compile(r"\d{8}")
_REGION_RE = re.compile(r"[a-z0-9-]{1,32}")
_HEADER_NAME_RE = re.compile(r"[a-z0-9-]{1,64}")
_SIGNATURE_RE = re.compile(r"[0-9a-f]{64}")
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_MAX_SIGNED_HEADERS = 64
MAX_CLOCK_SKEW = timedelta(hours=24)


class MalformedAuthorization(ValueError):
    """Cabeçalho `Authorization` ausente, fora do formato SigV4 ou sem os cabeçalhos assinados obrigatórios."""


@dataclass(frozen=True)
class ParsedAuthorization:
    access_key: str
    date: str
    region: str
    signed_headers: tuple[str, ...]
    signature: str = ""

    @property
    def scope(self) -> str:
        return f"{self.date}/{self.region}/{SERVICE}/aws4_request"


def parse_authorization(header: str | None) -> ParsedAuthorization:
    """Valida e decompõe `AWS4-HMAC-SHA256 Credential=..., SignedHeaders=..., Signature=...`."""
    if not header or not header.startswith(ALGORITHM + " "):
        raise MalformedAuthorization("algorithm")
    fields: dict[str, str] = {}
    for part in header[len(ALGORITHM) :].split(","):
        name, sep, value = part.strip().partition("=")
        if not sep or name in fields:
            raise MalformedAuthorization("fields")
        fields[name] = value.strip()
    if set(fields) != {"Credential", "SignedHeaders", "Signature"}:
        raise MalformedAuthorization("fields")
    credential = fields["Credential"].split("/")
    if len(credential) != 5:
        raise MalformedAuthorization("credential")
    access_key, date, region, service, terminator = credential
    valid_scope = (
        bool(access_key)
        and len(access_key) <= 128
        and _DATE_RE.fullmatch(date) is not None
        and _REGION_RE.fullmatch(region) is not None
        and service == SERVICE
        and terminator == "aws4_request"
    )
    if not valid_scope:
        raise MalformedAuthorization("credential")
    signed = tuple(fields["SignedHeaders"].split(";"))
    if (
        len(signed) > _MAX_SIGNED_HEADERS
        or list(signed) != sorted(set(signed))
        or not all(_HEADER_NAME_RE.fullmatch(h) for h in signed)
        or not REQUIRED_SIGNED_HEADERS <= set(signed)
    ):
        raise MalformedAuthorization("signed_headers")
    if _SIGNATURE_RE.fullmatch(fields["Signature"]) is None:
        raise MalformedAuthorization("signature")
    return ParsedAuthorization(access_key, date, region, signed, fields["Signature"])


def valid_amz_date(amz_date: str | None, auth: ParsedAuthorization, now: datetime | None = None) -> bool:
    """`X-Amz-Date` bem formado, do mesmo dia do escopo da credencial e a até 24 h do relógio do backend."""
    if not amz_date or _AMZ_DATE_RE.fullmatch(amz_date) is None or amz_date[:8] != auth.date:
        return False
    try:
        stamp = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return abs((now or datetime.now(UTC)) - stamp) <= MAX_CLOCK_SKEW


def payload_hash(body: bytes, declared: str | None) -> str | None:
    """Hash do corpo que entra na assinatura; `None` se o `x-amz-content-sha256` declarado não confere com o corpo.

    Sem o cabeçalho vale o SHA-256 do corpo. `UNSIGNED-PAYLOAD` e qualquer valor que não seja o SHA-256 do corpo
    são recusados.
    """
    actual = hashlib.sha256(body).hexdigest()
    if declared is None:
        return actual
    if _SHA256_HEX_RE.fullmatch(declared) and hmac.compare_digest(declared, actual):
        return actual
    return None


def _canonical_query(query: str) -> str:
    pairs = sorted((quote(k, safe=""), quote(v, safe="")) for k, v in parse_qsl(query, keep_blank_values=True))
    return "&".join(f"{k}={v}" for k, v in pairs)


def canonical_request(
    method: str,
    raw_path: str,
    query: str,
    header_values: Callable[[str], Sequence[str]],
    signed_headers: Sequence[str],
    body_hash: str,
) -> str | None:
    """Requisição canônica; `None` se algum cabeçalho assinado não veio na requisição.

    `raw_path` é o caminho como chegou (já codificado); serviços não-S3 o codificam de novo.
    """
    lines: list[str] = []
    for name in signed_headers:
        values = header_values(name)
        if not values:
            return None
        lines.append(f"{name}:{','.join(' '.join(v.split()) for v in values)}\n")
    path = quote(raw_path or "/", safe="/")
    return "\n".join([method.upper(), path, _canonical_query(query), "".join(lines), ";".join(signed_headers), body_hash])


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def signature_for(secret: str, amz_date: str, auth: ParsedAuthorization, canonical: str) -> str:
    """Assinatura SigV4 esperada (hex) para o segredo e a requisição canônica."""
    to_sign = "\n".join([ALGORITHM, amz_date, auth.scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(("AWS4" + secret).encode(), auth.date)
    for part in (auth.region, SERVICE, "aws4_request"):
        key = _hmac(key, part)
    return hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
