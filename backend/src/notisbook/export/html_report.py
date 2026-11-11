"""Self-contained HTML report export: no JavaScript, strict CSP, sanitized markdown and outputs."""

import base64
import binascii
import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from html import escape
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import nh3
from markdown_it import MarkdownIt
from pygments.lexer import Lexer
from pygments.lexers import PythonLexer, SqlLexer
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    _TokenType,
)

from .common import cell_language, cell_source

MAX_IMAGE_BYTES = 10 * 1024 * 1024
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
LANGUAGE_LABELS = {"python": "Python", "sql": "Spark SQL", "duckdb": "DuckDB SQL"}
WARNING_UNSUPPORTED = "saída não exportável"
_STAMP_FORMAT = "%d/%m/%Y %H:%M:%S"
_LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect x="0.5" y="0.5" width="99" height="99" rx="22" fill="#ffffff" stroke="#d9d9d5"/>
<rect x="16" y="16" width="17.4" height="17.4" fill="#111111"/>
<rect x="67" y="16" width="17.4" height="17.4" fill="#111111"/>
<rect x="16" y="33" width="17.4" height="17.4" fill="#111111"/>
<rect x="67" y="33" width="17.4" height="17.4" fill="#111111"/>
<rect x="16" y="50" width="17.4" height="17.4" fill="#111111"/>
<rect x="67" y="50" width="17.4" height="17.4" fill="#111111"/>
<rect x="16" y="67" width="17.4" height="17.4" fill="#111111"/>
<rect x="67" y="67" width="17.4" height="17.4" fill="#111111"/>
<rect x="33" y="33" width="17.4" height="17.4" fill="#7fb800"/>
<rect x="50" y="50" width="17.4" height="17.4" fill="#7fb800"/>
</svg>
"""
_LOGO_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_ALLOWED_CLASSES = {"nb-grid", "num", "null", "nb-grid-footer", "dataframe"}
_CLASS_TAGS = ("div", "span", "table", "thead", "tbody", "tr", "th", "td", "pre", "code", "p")
_SANITIZE: dict[str, Any] = {
    "clean_content_tags": {"script", "style"},
    "attributes": {
        "a": {"href", "title"},
        "img": {"src", "alt"},
        "td": {"colspan", "rowspan"},
        "th": {"colspan", "rowspan"},
    },
    "allowed_classes": {tag: set(_ALLOWED_CLASSES) for tag in _CLASS_TAGS},
    "url_schemes": {"http", "https", "mailto"},
    "url_relative": "deny",
}
_MARKDOWN = MarkdownIt("js-default")

# Tipos do Pygments -> classes curtas, nos mesmos grupos de cor de editorTheme.ts.
# A busca sobe pela hierarquia do token; o que não casa (Name.Builtin, texto) fica sem cor.
_TOKEN_CLASSES: dict[_TokenType, str] = {
    Keyword: "t-kw",
    Keyword.Type: "t-type",
    Operator.Word: "t-kw",
    Name.Builtin.Pseudo: "t-kw",
    Name.Function: "t-def",
    Name.Class: "t-type",
    Name.Namespace: "t-type",
    Name.Exception: "t-type",
    Name.Decorator: "t-meta",
    Comment: "t-com",
    Comment.Preproc: "t-meta",
    String: "t-str",
    Number: "t-num",
    Operator: "t-op",
    Punctuation: "t-op",
}
_CALLABLE_NAMES = (Name, Name.Builtin)

_CSS = """
/* Paleta --syntax-* duplicada de frontend/src/components/notebook/Notebook.module.css; os dois precisam andar juntos. */
:root{color-scheme:light dark;--syntax-keyword:#8839ef;--syntax-string:#2b8a3e;--syntax-number:#c2410c;--syntax-comment:#8a8a85;--syntax-function:#1d4ed8;--syntax-definition:#0f5ea8;--syntax-type:#b45309;--syntax-punctuation:#6b6b68;--syntax-meta:#a21caf;--syntax-property:#0e7490;--syntax-heading:#1f1f1e;--syntax-link:#3451b2;--color-border-strong:#8a8f98;--bg:#fff;--fg:#1f2328;--muted:#656d76;--code-bg:#f6f8fa;--err:#cf222e;--err-bg:#ffebe9}
@media (prefers-color-scheme:dark){:root{--syntax-keyword:#c4a7ff;--syntax-string:#8bd49c;--syntax-number:#f5a97f;--syntax-comment:#7d7d79;--syntax-function:#8cb4ff;--syntax-definition:#7ec8ff;--syntax-type:#f2c46d;--syntax-punctuation:#a3a3a0;--syntax-meta:#f0a6f5;--syntax-property:#76d7e4;--syntax-heading:#ececea;--syntax-link:#9db4f8;--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--code-bg:#161b22;--err:#ff7b72;--err-bg:#3d1214}}
body{margin:0 auto;max-width:960px;padding:24px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header{border-bottom:1px solid var(--color-border-strong);margin-bottom:16px}
header p{color:var(--muted);margin:4px 0 12px}
nav ul{list-style:none;padding-left:0}nav li.l2{margin-left:16px}nav li.l3{margin-left:32px}
section.cell{margin:16px 0}
.lang{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
pre{background:var(--code-bg);padding:10px 12px;overflow-x:auto;border-radius:6px;margin:4px 0;white-space:pre-wrap;word-break:break-word}
.t-kw{color:var(--syntax-keyword)}.t-str{color:var(--syntax-string)}.t-num{color:var(--syntax-number)}
.t-com{color:var(--syntax-comment);font-style:italic}.t-fn{color:var(--syntax-function)}.t-def{color:var(--syntax-definition)}
.t-type{color:var(--syntax-type)}.t-op{color:var(--syntax-punctuation)}.t-meta{color:var(--syntax-meta)}
.out{margin:6px 0 0 12px;overflow-x:auto}
.stderr,.error{background:var(--err-bg);color:var(--err);border-left:3px solid var(--err)}
.warn{color:var(--muted);font-style:italic}
img{max-width:100%}
table{border-collapse:collapse}
td,th{padding:4px 10px;text-align:left}
.nb-grid th,.nb-grid td,.dataframe th,.dataframe td{border:1px solid var(--color-border-strong)}
.nb-grid{overflow-x:auto}
.nb-grid th,.nb-grid td,.dataframe th,.dataframe td{white-space:nowrap}
.nb-grid th.num,.nb-grid td.num{text-align:right}
.nb-grid thead th,.dataframe thead th{border-bottom:2px solid var(--color-border-strong)}
.nb-grid .null{color:var(--muted);font-style:italic}
.nb-grid-footer{padding:6px 10px;font-size:12px;color:var(--muted)}
footer{margin-top:24px;padding-top:8px;border-top:1px solid var(--color-border-strong);font-size:12px;color:var(--muted)}
footer img{width:16px;height:16px;vertical-align:text-bottom}
@media print{body{max-width:none;padding:0}.out,.nb-grid{overflow:visible}.nb-grid td,.nb-grid th,.dataframe td,.dataframe th{font-size:7.5pt;padding:1px 3px}pre{white-space:pre-wrap}section.cell{break-inside:avoid-page}nav{display:none}}
"""


def _text(value: Any) -> str:
    return "".join(value) if isinstance(value, list) else str(value or "")


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _sanitize(html: str) -> str:
    return nh3.clean(html, **_SANITIZE)


def _warn(message: str) -> str:
    return f'<p class="warn">{escape(message)}</p>'


def _pre(text: str, css: str = "") -> str:
    cls = f' class="{css}"' if css else ""
    return f"<pre{cls}>{escape(text)}</pre>"


def _heading_text(inline: Any) -> str:
    parts = [c.content for c in (inline.children or []) if c.type in ("text", "code_inline")]
    return "".join(parts).strip()


def _render_markdown(source: str) -> tuple[str, list[tuple[int, str]]]:
    tokens = _MARKDOWN.parse(source)
    headings = [
        (int(tok.tag[1]), _heading_text(tokens[i + 1]))
        for i, tok in enumerate(tokens)
        if tok.type == "heading_open" and int(tok.tag[1]) <= 3 and i + 1 < len(tokens)
    ]
    html = _MARKDOWN.renderer.render(tokens, _MARKDOWN.options, {})
    return _sanitize(html), [(level, text) for level, text in headings if text]


def _image(mime: str, value: Any) -> str:
    raw_b64 = re.sub(r"\s+", "", _text(value))
    if len(raw_b64) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        return _warn("imagem acima de 10 MB não incluída")
    try:
        data = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError):
        return _warn(WARNING_UNSUPPORTED)
    if len(data) > MAX_IMAGE_BYTES:
        return _warn("imagem acima de 10 MB não incluída")
    clean = base64.b64encode(data).decode("ascii")
    return f'<img src="data:{mime};base64,{clean}" alt="saída da célula">'


def _svg_image(value: Any) -> str:
    data = _text(value).encode("utf-8")
    if len(data) > MAX_IMAGE_BYTES:
        return _warn("imagem acima de 10 MB não incluída")
    return f'<img src="data:image/svg+xml;base64,{base64.b64encode(data).decode("ascii")}" alt="saída da célula">'


def _render_bundle(data: dict[str, Any]) -> str:
    if "text/html" in data:
        return _sanitize(_text(data["text/html"]))
    for mime in ("image/png", "image/jpeg"):
        if mime in data:
            return _image(mime, data[mime])
    if "image/svg+xml" in data:
        return _svg_image(data["image/svg+xml"])
    if "text/markdown" in data:
        return _render_markdown(_text(data["text/markdown"]))[0]
    if "text/plain" in data:
        return _pre(_strip_ansi(_text(data["text/plain"])))
    return _warn(WARNING_UNSUPPORTED)


def _render_output(output: dict[str, Any]) -> str:
    kind = output.get("output_type")
    if kind == "stream":
        css = "stderr" if output.get("name") == "stderr" else ""
        return _pre(_strip_ansi(_text(output.get("text"))), css)
    if kind in ("display_data", "execute_result"):
        data = output.get("data")
        return _render_bundle(data if isinstance(data, dict) else {})
    if kind == "error":
        head = f"{_text(output.get('ename'))}: {_text(output.get('evalue'))}"
        trace = "\n".join(_text(line) for line in output.get("traceback") or [])
        return _pre(_strip_ansi(f"{head}\n{trace}".strip()), "error")
    return _warn(WARNING_UNSUPPORTED)


def _token_class(ttype: _TokenType, sql: bool) -> str:
    if sql and ttype is Name.Builtin:
        return "t-type"
    while ttype not in _TOKEN_CLASSES:
        if ttype.parent is None:
            return ""
        ttype = ttype.parent
    return _TOKEN_CLASSES[ttype]


def _call_flags(tokens: list[tuple[_TokenType, str]]) -> list[bool]:
    """Para cada posição, se o próximo token não-branco começa com "(" (uma passada, de trás para frente)."""
    flags = [False] * len(tokens)
    following = False
    for i in range(len(tokens) - 1, -1, -1):
        flags[i] = following
        value = tokens[i][1]
        if value.strip():
            following = value.startswith("(")
    return flags


def _highlight_code(source: str, language: str) -> str:
    """Escape `source` and wrap tokens in `<span class="t-*">`; the text never becomes markup."""
    sql = language != "python"
    lexer: Lexer = (SqlLexer if sql else PythonLexer)(stripnl=False, ensurenl=False)
    tokens = list(lexer.get_tokens(source))
    calls = _call_flags(tokens)
    # Tokens vizinhos de mesma classe viram um só span; acumula em lista e junta uma vez
    # por grupo (concatenar a string a cada token seria quadrático).
    parts: list[tuple[str, list[str]]] = []
    for i, (ttype, value) in enumerate(tokens):
        css = _token_class(ttype, sql)
        # Chamada de função (nome seguido de "("): o Pygments só marca a definição.
        # Em SQL, Name.Builtin é tipo (VARCHAR(10)) e não vira função.
        if calls[i] and ttype in _CALLABLE_NAMES and not (sql and ttype is Name.Builtin):
            css = "t-fn"
        if parts and parts[-1][0] == css:
            parts[-1][1].append(value)
        else:
            parts.append((css, [value]))
    texts = ((css, "".join(chunks)) for css, chunks in parts)
    return "".join(f'<span class="{css}">{escape(text)}</span>' if css else escape(text) for css, text in texts)


def _render_cell(n: int, cell: dict[str, Any]) -> tuple[str, list[tuple[int, str, int]]]:
    source = cell_source(cell)
    outputs = cell.get("outputs") if isinstance(cell.get("outputs"), list) else []
    if not source.strip() and not outputs:
        return "", []
    headings: list[tuple[int, str, int]] = []
    if cell.get("cell_type") == "markdown":
        body, found = _render_markdown(source)
        headings = [(level, text, n) for level, text in found]
        inner = f'<div class="md">{body}</div>'
    elif cell.get("cell_type") == "code":
        label = LANGUAGE_LABELS[cell_language(cell)]
        inner = f'<div class="lang">{label}</div><pre><code>{_highlight_code(source, cell_language(cell))}</code></pre>'
        inner += "".join(f'<div class="out">{_render_output(o)}</div>' for o in outputs if isinstance(o, dict))
    else:
        inner = _pre(source)
    return f'<section class="cell" id="cell-{n}">{inner}</section>', headings


def _brasilia_tz() -> tzinfo:
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        # Sem tzdata no sistema; o Brasil não adota horário de verão desde 2019.
        return timezone(timedelta(hours=-3))


def _stamp(moment: datetime | None) -> str:
    """Format `moment` (naive is taken as UTC) as dd/mm/aaaa HH:MM:SS in Brasília time."""
    base = moment or datetime.now(UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return base.astimezone(_brasilia_tz()).strftime(_STAMP_FORMAT)


def _footer(stamp: str) -> str:
    logo = f'<img src="{_LOGO_DATA_URI}" alt="Notisbook" width="16" height="16">'
    return f"<footer>Exportado pelo {logo} Notisbook em {escape(stamp)} (horário de Brasília)</footer>"


def _meta_lines(notebook: dict[str, Any], stamp: str, cell_count: int) -> str:
    meta = notebook.get("metadata") if isinstance(notebook.get("metadata"), dict) else {}
    parts = [f"Exportado em {stamp} (horário de Brasília)"]
    kernelspec = meta.get("kernelspec") if isinstance(meta.get("kernelspec"), dict) else {}
    kernel = kernelspec.get("display_name") or kernelspec.get("name")
    if kernel:
        parts.append(f"Kernel: {kernel}")
    info = meta.get("language_info") if isinstance(meta.get("language_info"), dict) else {}
    if info.get("name"):
        parts.append(f"Ambiente: {info['name']} {info.get('version', '')}".strip())
    parts.append(f"{cell_count} células")
    return " · ".join(escape(str(p)) for p in parts)


def _title(name: str) -> str:
    last = re.split(r"[/\\]", name)[-1]
    stem = last[: -len(".ipynb")] if last.endswith(".ipynb") else last
    return stem.strip() or "Notebook"


def to_html_report(notebook: dict[str, Any], name: str, generated_at: datetime | None = None) -> bytes:
    """Render `notebook` as one UTF-8 HTML document; `name` only supplies the title."""
    stamp = _stamp(generated_at)
    cells = notebook.get("cells", [])
    sections: list[str] = []
    toc: list[tuple[int, str, int]] = []
    for n, cell in enumerate(cells, start=1):
        html, headings = _render_cell(n, cell)
        if html:
            sections.append(html)
            toc.extend(headings)
    title = escape(_title(name))
    nav = ""
    if toc:
        items = "".join(f'<li class="l{lv}"><a href="#cell-{n}">{escape(t)}</a></li>' for lv, t, n in toc)
        nav = f"<nav><strong>Índice</strong><ul>{items}</ul></nav>"
    page = (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>{title}</h1><p>{_meta_lines(notebook, stamp, len(cells))}</p></header>"
        f"{nav}<main>{''.join(sections)}</main>{_footer(stamp)}</body></html>"
    )
    return page.encode("utf-8")
