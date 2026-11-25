"""Self-contained HTML report export: no JavaScript, strict CSP, sanitized markdown and outputs."""

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from html import escape
from importlib import resources
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

from ..kernels.languages import CELL_LANGUAGE_LABELS
from .common import cell_language, cell_source

MAX_IMAGE_BYTES = 10 * 1024 * 1024
CSP = "default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'"
WARNING_UNSUPPORTED = "saída não exportável"
_STAMP_FORMAT = "%d/%m/%Y %H:%M:%S"
_REPO_URL = "https://github.com/ROM-mm/Notisbook"

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

DEFAULT_CODE_FONT = "VT323"
DEFAULT_MARKDOWN_FONT = "Roboto"
MAX_FONT_NAME = 64
# Mesma regra de FONT_NAME_PATTERN (frontend/src/state/appearance.ts): nada que escape de uma string CSS entre aspas.
_FONT_NAME = re.compile(r"[^\"'\\;{}\x00-\x1f\x7f]+")
_CODE_FALLBACK = "ui-monospace, SFMono-Regular, Menlo, monospace"
_MARKDOWN_FALLBACK = 'system-ui, -apple-system, "Segoe UI", sans-serif'
_LATIN_RANGE = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
    "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
)
_LATIN_EXT_RANGE = (
    "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,"
    "U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"
)


@dataclass(frozen=True)
class _FontFile:
    file: str
    weight: str
    style: str = "normal"
    unicode_range: str = ""


def _roboto_files() -> tuple[_FontFile, ...]:
    variants = (("400", "normal"), ("500", "normal"), ("600", "normal"), ("700", "normal"))
    variants += (("400", "italic"), ("600", "italic"), ("700", "italic"))
    return tuple(
        _FontFile(f"roboto-{subset}-{weight}-{style}.woff2", weight, style, span)
        for subset, span in (("latin", _LATIN_RANGE), ("latin-ext", _LATIN_EXT_RANGE))
        for weight, style in variants
    )


# Famílias empacotadas em export/fonts/ (cópias das do app). O Roboto do fontsource não traz unicode-range e o
# subconjunto latin-ext não cobre ASCII: sem a faixa, a face declarada por último valeria para todo o texto.
_BUNDLED: dict[str, tuple[_FontFile, ...]] = {
    "VT323": (_FontFile("VT323-Regular.ttf", "400"),),
    "Monocode": (_FontFile("monocode-regular.woff2", "400"), _FontFile("monocode-medium.woff2", "500 700")),
    "Roboto": _roboto_files(),
}
_FONT_FORMATS = {".ttf": ("font/ttf", "truetype"), ".woff2": ("font/woff2", "woff2")}


def validate_font_name(name: str) -> str:
    """Return `name` if it is safe to place inside a quoted CSS font-family; raise ValueError otherwise."""
    if name != name.strip() or not 0 < len(name) <= MAX_FONT_NAME or not _FONT_NAME.fullmatch(name):
        raise ValueError("invalid font name")
    return name


@dataclass(frozen=True)
class ExportFonts:
    """Font names chosen for code/outputs and markdown text; validated on construction."""

    code: str = DEFAULT_CODE_FONT
    markdown: str = DEFAULT_MARKDOWN_FONT

    def __post_init__(self) -> None:
        validate_font_name(self.code)
        validate_font_name(self.markdown)


@lru_cache(maxsize=None)
def _font_base64(file: str) -> str:
    data = resources.files(__package__).joinpath("fonts", file).read_bytes()
    return base64.b64encode(data).decode("ascii")


@lru_cache(maxsize=None)
def _font_face_css(family: str) -> str:
    rules = []
    for face in _BUNDLED[family]:
        mime, fmt = _FONT_FORMATS[face.file[face.file.rindex(".") :]]
        extra = f"unicode-range:{face.unicode_range};" if face.unicode_range else ""
        if family == DEFAULT_CODE_FONT:
            extra += "size-adjust:140%;"
        rules.append(
            f'@font-face{{font-family:"{family}";src:url(data:{mime};base64,{_font_base64(face.file)}) format("{fmt}");'
            f"font-weight:{face.weight};font-style:{face.style};font-display:swap;{extra}}}"
        )
    return "\n".join(rules)


def _css_string(name: str) -> str:
    # Dentro de <style> o texto é cru: "<" vira escape CSS para não fechar o elemento (nome já validado).
    return '"' + name.replace("<", "\\3c ") + '"'


def _font_stack(name: str, default: str, fallback: str) -> str:
    """Bundled font: its name plus generics. Other name: it, then the slot's bundled default, then generics."""
    head = [_css_string(name)] if name in _BUNDLED else [_css_string(name), _css_string(default)]
    return ", ".join([*head, fallback])


def _font_css(fonts: ExportFonts) -> str:
    """`@font-face` rules (only the families in use) and the `:root` variables read by `_CSS`."""
    families: list[str] = []
    for name, default in ((fonts.code, DEFAULT_CODE_FONT), (fonts.markdown, DEFAULT_MARKDOWN_FONT)):
        wanted = name if name in _BUNDLED else default
        if wanted not in families:
            families.append(wanted)
    code = _font_stack(fonts.code, DEFAULT_CODE_FONT, _CODE_FALLBACK)
    markdown = _font_stack(fonts.markdown, DEFAULT_MARKDOWN_FONT, _MARKDOWN_FALLBACK)
    faces = "\n".join(_font_face_css(family) for family in families)
    return f"{faces}\n:root{{--font-code:{code};--font-markdown:{markdown}}}\n"


# Pygments -> classes curtas (grupos de cor de editorTheme.ts); a busca sobe pela hierarquia. Sem correspondência
# herda a cor base de pre>code (--syntax-variable): texto e Name.Builtin em Python fora de chamada (em SQL vai
# para t-type; seguido de "(" vira t-fn). True/False/None seguem a cor de número; o nome em def/class, a de chamada.
_TOKEN_CLASSES: dict[_TokenType, str] = {
    Keyword: "t-kw",
    Keyword.Constant: "t-num",
    Keyword.Type: "t-type",
    Operator.Word: "t-op",
    Name.Builtin.Pseudo: "t-kw",
    Name.Function: "t-fn",
    Name.Class: "t-fn",
    Name.Namespace: "t-op",
    Name.Exception: "t-cls",
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
/* Escala de cinzas de frontend/src/styles/tokens.css (--sx-code-* e --sx-dark-code-*), fonte da paleta;
   o código da célula (pre>code) tem cor base --syntax-variable, como identificador no app; as classes t-* sobrepõem
   por papel e pontuação/operador usa --syntax-text. Ao mudar a paleta, atualize os dois.
   O export não porta os papéis do app: no escuro, colunas/tabelas SQL e classes Python sem marcação saem
   na cor de variável (#838383), e no app em #ffffff. */
:root{color-scheme:light dark;--syntax-keyword:#767676;--syntax-text:#2b2b2b;--syntax-variable:#111111;--syntax-function:#4d4d4d;--syntax-string:#6a6a6a;--syntax-number:#5e5e5e;--syntax-comment:#949494;--syntax-type:#3c3c3c;--syntax-class:#3c3c3c;--color-border-strong:#8a8f98;--bg:#fff;--fg:#1f2328;--muted:#656d76;--code-bg:#f6f8fa;--err:#cf222e;--err-bg:#ffebe9}
@media (prefers-color-scheme:dark){:root{--syntax-keyword:#808080;--syntax-text:#ffffff;--syntax-variable:#838383;--syntax-function:#868686;--syntax-string:#8e8e8e;--syntax-number:#999999;--syntax-comment:#616161;--syntax-type:#a0a0a0;--syntax-class:#ffffff;--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--code-bg:#161b22;--err:#ff7b72;--err-bg:#3d1214}}
body{margin:0 auto;max-width:960px;padding:24px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header{border-bottom:1px solid var(--color-border-strong);margin-bottom:16px}
header p{color:var(--muted);margin:4px 0 12px}
nav ul{list-style:none;padding-left:0}nav li.l2{margin-left:16px}nav li.l3{margin-left:32px}
section.cell{margin:16px 0}
.lang{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
pre{background:var(--code-bg);padding:10px 12px;overflow-x:auto;border-radius:6px;margin:4px 0;white-space:pre-wrap;word-break:break-word}
pre>code{color:var(--syntax-variable)}
pre,pre>code,.out,.nb-grid,.dataframe,.md code,.md pre{font-family:var(--font-code);font-synthesis:none}
.md{font-family:var(--font-markdown)}
.t-kw{color:var(--syntax-keyword)}.t-str{color:var(--syntax-string)}.t-num{color:var(--syntax-number)}
.t-com{color:var(--syntax-comment)}.t-fn{color:var(--syntax-function)}
.t-type{color:var(--syntax-type)}.t-cls{color:var(--syntax-class)}.t-op{color:var(--syntax-text)}.t-meta{color:var(--syntax-keyword)}
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
footer .logo-dark{display:none}
@media (prefers-color-scheme:dark){footer .logo-light{display:none}footer .logo-dark{display:inline}}
footer a{color:inherit}
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
        label = CELL_LANGUAGE_LABELS[cell_language(cell)]
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


@lru_cache(maxsize=None)
def _brand_data_uri(file: str) -> str:
    data = resources.files(__package__).joinpath("brand", file).read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")


def _footer() -> str:
    # Duas imagens decorativas; o CSS mostra só a do tema ativo (sem JS, CSP inalterada).
    logo = "".join(
        f'<img class="logo-{variant}" src="{_brand_data_uri(f"favicon-{variant}.svg")}" alt="" width="16" height="16">'
        for variant in ("light", "dark")
    )
    link = f'<a href="{_REPO_URL}" target="_blank" rel="noopener noreferrer">{_REPO_URL}</a>'
    return f"<footer>Exported by {logo} Notisbook {link}</footer>"


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


def to_html_report(
    notebook: dict[str, Any],
    name: str,
    generated_at: datetime | None = None,
    fonts: ExportFonts | None = None,
) -> bytes:
    """Render `notebook` as one UTF-8 HTML document; `name` only supplies the title.

    `fonts` picks the code and markdown fonts (default VT323/Roboto). Bundled families are embedded as base64.
    """
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
        f"<title>{title}</title><style>{_font_css(fonts or ExportFonts())}{_CSS}</style></head><body>"
        f"<header><h1>{title}</h1><p>{_meta_lines(notebook, stamp, len(cells))}</p></header>"
        f"{nav}<main>{''.join(sections)}</main>{_footer()}</body></html>"
    )
    return page.encode("utf-8")
