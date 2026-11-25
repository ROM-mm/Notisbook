"""Filtro `Expression` do GetPartitions: parser próprio de um subconjunto seguro do SQL de partições do Glue.

Gramática: comparações `chave (= | != | <> | < | <= | > | >=) literal`, `chave IN (literal, ...)`, `AND`, `OR` e
parênteses (AND liga mais forte que OR). Literal é texto entre aspas simples (`''` escapa a aspa) ou número. As chaves
precisam ser chaves de partição da tabela. Qualquer outra construção (LIKE, BETWEEN, NOT, funções...) é recusada com
`GlueInvalidInput`: o filtro nunca é ignorado em silêncio. Não usa `eval`; o tokenizador é um padrão fixo.
Colunas numéricas comparam como `Decimal`; as demais, como texto.
"""

import re
from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from .glue_repo import GlueInvalidInput

MAX_EXPRESSION_CHARS = 2048
MAX_DEPTH = 20
MAX_IN_ITEMS = 256

Predicate = Callable[[Sequence[str]], bool]

_TOKEN_RE = re.compile(
    r"""\s*(?:
    (?P<string>'(?:[^']|'')*')
  | (?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<op><=|>=|<>|!=|=|<|>)
  | (?P<punct>[(),])
  | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
    )""",
    re.VERBOSE,
)
_NUMERIC_TYPES = ("tinyint", "smallint", "int", "integer", "bigint", "float", "double", "decimal", "dec", "numeric")
_COMPARISONS: dict[str, Callable[[Any, Any], bool]] = {
    "=": lambda a, b: bool(a == b),
    "!=": lambda a, b: bool(a != b),
    "<>": lambda a, b: bool(a != b),
    "<": lambda a, b: bool(a < b),
    "<=": lambda a, b: bool(a <= b),
    ">": lambda a, b: bool(a > b),
    ">=": lambda a, b: bool(a >= b),
}


def _refuse(message: str) -> GlueInvalidInput:
    return GlueInvalidInput("unsupported_expression", message)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        if not text[pos:].strip():
            break
        match = _TOKEN_RE.match(text, pos)
        if match is None or match.end() == pos:
            raise _refuse("Unsupported character in partition expression.")
        kind = match.lastgroup or ""
        tokens.append((kind, match.group(kind)))
        pos = match.end()
    return tokens


class _Column:
    """Chave de partição: posição em `Values` e se compara como número."""

    def __init__(self, index: int, numeric: bool) -> None:
        self.index = index
        self.numeric = numeric


def _columns(keys: Sequence[dict[str, Any]]) -> dict[str, _Column]:
    out: dict[str, _Column] = {}
    for index, key in enumerate(keys):
        name = key.get("Name")
        if not isinstance(name, str):
            continue
        base = str(key.get("Type") or "string").lower().split("(", 1)[0].strip()
        out[name.lower()] = _Column(index, base in _NUMERIC_TYPES)
    return out


def _decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], columns: dict[str, _Column]) -> None:
        self._tokens = tokens
        self._columns = columns
        self._pos = 0
        self._depth = 0

    def parse(self) -> Predicate:
        predicate = self._or()
        if self._pos != len(self._tokens):
            raise _refuse("Unexpected token in partition expression.")
        return predicate

    def _peek(self) -> tuple[str, str] | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise _refuse("Partition expression ended unexpectedly.")
        self._pos += 1
        return token

    def _keyword(self, word: str) -> bool:
        token = self._peek()
        if token is not None and token[0] == "word" and token[1].upper() == word:
            self._pos += 1
            return True
        return False

    def _punct(self, char: str) -> bool:
        if self._peek() == ("punct", char):
            self._pos += 1
            return True
        return False

    def _or(self) -> Predicate:
        parts = [self._and()]
        while self._keyword("OR"):
            parts.append(self._and())
        return parts[0] if len(parts) == 1 else (lambda values: any(p(values) for p in parts))

    def _and(self) -> Predicate:
        parts = [self._primary()]
        while self._keyword("AND"):
            parts.append(self._primary())
        return parts[0] if len(parts) == 1 else (lambda values: all(p(values) for p in parts))

    def _primary(self) -> Predicate:
        if self._punct("("):
            self._depth += 1
            if self._depth > MAX_DEPTH:
                raise _refuse("Partition expression is nested too deeply.")
            inner = self._or()
            if not self._punct(")"):
                raise _refuse("Missing closing parenthesis in partition expression.")
            self._depth -= 1
            return inner
        kind, text = self._take()
        column = self._columns.get(text.lower()) if kind == "word" else None
        if column is None:
            raise _refuse("Partition expression must compare a partition key.")
        if self._keyword("IN"):
            return self._in(column)
        kind, op = self._take()
        if kind != "op":
            raise _refuse("Unsupported operator in partition expression.")
        literal = self._literal(column)
        compare = _COMPARISONS[op]
        index = column.index
        return lambda values: _safe(compare, _cell(values, index, column), literal)

    def _in(self, column: _Column) -> Predicate:
        if not self._punct("("):
            raise _refuse("IN must be followed by a parenthesized list.")
        items = [self._literal(column)]
        while self._punct(","):
            items.append(self._literal(column))
            if len(items) > MAX_IN_ITEMS:
                raise _refuse("IN list is too long.")
        if not self._punct(")"):
            raise _refuse("Missing closing parenthesis in IN list.")
        index = column.index
        return lambda values: any(_safe(_COMPARISONS["="], _cell(values, index, column), item) for item in items)

    def _literal(self, column: _Column) -> Any:
        kind, text = self._take()
        if kind == "string":
            raw = text[1:-1].replace("''", "'")
        elif kind == "number":
            raw = text
        else:
            raise _refuse("Partition expression compares only with literals.")
        if not column.numeric:
            return raw
        number = _decimal(raw)
        if number is None:
            raise _refuse("Literal is not numeric for a numeric partition key.")
        return number


def _cell(values: Sequence[str], index: int, column: _Column) -> Any:
    if index >= len(values):
        return None
    return _decimal(values[index]) if column.numeric else values[index]


def _safe(compare: Callable[[Any, Any], bool], left: Any, right: Any) -> bool:
    """Valor de partição que não converte (ex.: `__HIVE_DEFAULT_PARTITION__` em coluna numérica) não casa com nada."""
    return left is not None and compare(left, right)


def compile_expression(expression: Any, partition_keys: Sequence[dict[str, Any]]) -> Predicate | None:
    """Predicado sobre `Values` da partição, ou `None` para `Expression` ausente/vazia (sem filtro).

    Levanta `GlueInvalidInput` (`unsupported_expression`) para sintaxe, operador ou chave fora do subconjunto.
    """
    if expression is None:
        return None
    if not isinstance(expression, str):
        raise GlueInvalidInput("invalid_payload", "Expression must be a string.")
    if not expression.strip():
        return None
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise _refuse("Partition expression is too long.")
    return _Parser(_tokenize(expression), _columns(partition_keys)).parse()
