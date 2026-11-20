"""Databricks "notebook source" (.py) export. Spark SQL becomes `spark.sql`, DuckDB stays as comments."""

import re
from typing import Any

from .common import cell_language, cell_source

HEADER = "# Databricks notebook source"
SEPARATOR = "\n\n# COMMAND ----------\n\n"
DUCKDB_WARNING = "# NOTISBOOK: célula DuckDB SQL não convertida (sem equivalente no Spark). Original abaixo:"

_MAGIC_LINE = re.compile(r"%%?[A-Za-z]")
_CELL_MAGIC = re.compile(r"%%[A-Za-z]")
_BLOCK_COMMENT =re.compile(r"/\*.*?\*/", re.DOTALL)
_ECHO_CALL = re.compile(r"(?<![\w.])echo[ \t]*\(")
_DEF_BEFORE = re.compile(r"\bdef[ \t]+$")
_N_KWARG = re.compile(r"n\s*=(?!=)")
_CLOSERS = {"(": ")", "[": "]", "{": "}"}


def _comment(text: str) -> str:
    return "\n".join(f"# {line}".rstrip() for line in text.split("\n"))


def _magic(text: str) -> str:
    return "\n".join(f"# MAGIC {line}".rstrip() for line in text.split("\n"))


def _triple_state(line: str, open_quote: str | None) -> str | None:
    """Delimitador de string tripla ainda aberto ao fim de `line` (None se nenhum); aproximação léxica."""
    i, n = 0, len(line)
    while i < n:
        if open_quote is not None:
            end = line.find(open_quote, i)
            if end == -1:
                return open_quote
            i, open_quote = end + 3, None
            continue
        ch = line[i]
        if ch == "#":
            break
        if ch in "'\"":
            if line.startswith(ch * 3, i):
                open_quote, i = ch * 3, i + 3
                continue
            i += 1
            while i < n and line[i] != ch:
                i += 2 if line[i] == "\\" else 1
        i += 1
    return open_quote


def _skip_string(text: str, i: int) -> int:
    """Índice logo após a string iniciada em `text[i]` (aspa simples ou tripla); fim do texto se não fechar."""
    quote = text[i] * 3 if text.startswith(text[i] * 3, i) else text[i]
    i += len(quote)
    while i < len(text):
        if text[i] == "\\" and len(quote) == 1:
            i += 2
        elif text.startswith(quote, i):
            return i + len(quote)
        else:
            i += 1
    return len(text)


def _call_args(text: str, start: int) -> tuple[list[str], int] | None:
    """Argumentos de topo da chamada cujo `(` abre antes de `start` e o índice após o `)`; None se não fechar."""
    args: list[str] = []
    stack = [")"]
    begin = i = start
    while i < len(text):
        ch = text[i]
        if ch in "'\"":
            i = _skip_string(text, i)
            continue
        if ch == "#":
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        if ch in _CLOSERS:
            stack.append(_CLOSERS[ch])
        elif ch in ")]}":
            if ch != stack.pop():
                return None
            if not stack:
                args.append(text[begin:i])
                return args, i + 1
        elif ch == "," and len(stack) == 1:
            args.append(text[begin:i])
            begin = i + 1
        i += 1
    return None


def _ends_in_comment(text: str) -> bool:
    """True se o fim de `text` está dentro de um comentário `#` real (não um `#` dentro de string)."""
    i = 0
    while i < len(text):
        if text[i] in "'\"":
            i = _skip_string(text, i)
        elif text[i] == "#":
            end = text.find("\n", i)
            if end == -1:
                return True
            i = end
        else:
            i += 1
    return False


def _drop_comment_lines(arg: str) -> str:
    return "\n".join(ln for ln in arg.split("\n") if not ln.lstrip().startswith("#"))


def _echo_to_display(source: str) -> str:
    """Traduz `echo(df, n=...)` para `display(df)`: o Databricks só tem `display`, sem `n=`."""
    out: list[str] = []
    i = last = 0
    while i < len(source):
        ch = source[i]
        if ch == "#":
            end = source.find("\n", i)
            i = len(source) if end == -1 else end
        elif ch in "'\"":
            i = _skip_string(source, i)
        else:
            match = _ECHO_CALL.match(source, i) if ch == "e" else None
            is_def = match is not None and _DEF_BEFORE.search(source, 0, i) is not None
            parsed = _call_args(source, match.end()) if match and not is_def else None
            if parsed is None:
                i += 1
                continue
            args, end = parsed
            kept = [a for a in args if not _N_KWARG.match(_drop_comment_lines(a).strip())]
            body = ",".join(kept).rstrip()
            if _ends_in_comment(body):
                body += "\n"  # evita que o `)` fique dentro de um comentário final
            out.append(source[last:i] + "display(" + body + ")")
            i = last = end
    out.append(source[last:])
    return "".join(out)


def _python_block(source: str) -> str:
    first = next((ln for ln in source.split("\n") if ln.strip()), "")
    if _CELL_MAGIC.match(first):
        return _magic(source)  # cell magic applies to the whole cell body
    source = _echo_to_display(source)
    lines: list[str] = []
    in_string: str | None = None  # linhas dentro de string tripla passam intactas
    for line in source.split("\n"):
        if in_string is None and _MAGIC_LINE.match(line):
            lines.append(f"# MAGIC {line}")
        elif in_string is None and line.startswith("!"):
            lines.append(f"# NOTISBOOK: comando de shell não convertido: {line}")
        else:
            lines.append(line)
            in_string = _triple_state(line, in_string)
    return "\n".join(lines)


def _is_comment_only(sql: str) -> bool:
    without_blocks = _BLOCK_COMMENT.sub("", sql)
    return all(not ln.strip() or ln.strip().startswith("--") for ln in without_blocks.split("\n"))


def _split_statements(sql: str) -> list[str] | None:
    """Split on `;` outside quotes, backticks and comments; None if a quote or block comment is unclosed."""
    statements: list[str] = []
    start = 0
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in "'\"`":
            i += 1
            while i < n and sql[i] != ch:
                i += 2 if sql[i] == "\\" and ch != "`" else 1
            if i >= n:
                return None
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end == -1:
                return None
            i = end + 1
        elif ch == ";":
            statements.append(sql[start:i])
            start = i + 1
        i += 1
    statements.append(sql[start:])
    return statements


def _spark_sql_call(statement: str) -> str:
    escaped = statement.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'spark.sql("""\n{escaped}\n""")'


def _spark_sql_block(sql: str) -> str:
    if _is_comment_only(sql):
        return _comment(sql)
    statements = _split_statements(sql)
    if statements is None:
        return _spark_sql_call(sql)
    parts = []
    for statement in statements:
        statement = statement.strip()
        if not statement:
            continue
        parts.append(_comment(statement) if _is_comment_only(statement) else _spark_sql_call(statement))
    return "\n".join(parts)


def _cell_block(cell: dict[str, Any]) -> str | None:
    source = cell_source(cell).strip("\n")
    if not source.strip():
        return None
    if cell.get("cell_type") == "markdown":
        return f"# MAGIC %md\n{_magic(source)}"
    if cell.get("cell_type") != "code":
        return _comment(source)
    language = cell_language(cell)
    if language == "sql":
        return _spark_sql_block(source)
    if language == "duckdb":
        return f"{DUCKDB_WARNING}\n{_comment(source)}"
    return _python_block(source)


def to_databricks_py(notebook: dict[str, Any]) -> bytes:
    """Render the notebook as UTF-8 Databricks source (no BOM, `\\n`, trailing newline)."""
    blocks = [b for c in notebook.get("cells", []) if (b := _cell_block(c)) is not None]
    body = HEADER + "\n" + SEPARATOR.join(blocks) if blocks else HEADER
    return (body.rstrip("\n") + "\n").encode("utf-8")
