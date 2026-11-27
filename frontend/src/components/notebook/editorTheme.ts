/**
 * Tema do CodeMirror 6 integrado aos tokens do app. Todas as cores são
 * `var(--...)`, então a troca claro/escuro (data-theme / prefers-color-scheme)
 * se aplica sem reconfigurar o editor. As cores de sintaxe (`--syntax-*`) são
 * definidas em `Notebook.module.css`, no contêiner do notebook.
 */
import { python, pythonLanguage } from "@codemirror/lang-python";
import { HighlightStyle, LanguageSupport, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate } from "@codemirror/view";
import { type EditorState, type Extension, Prec, type Range, type Text } from "@codemirror/state";
import { styleTags, tags as t } from "@lezer/highlight";

const theme = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    color: "var(--color-text)",
    fontSize: "13.5px",
  },
  // Papéis por decoração (`pythonRoleHighlight`, `sqlRoleHighlight`). O `*` vence o span da
  // tag do Lezer, aninhado dentro ou fora da marca.
  // Classe/tipo reconhecido, atributo de classe reconhecida (`SparkSession.builder`) e tipo SQL.
  ".cm-py-class, .cm-py-class *, .cm-py-class-attr, .cm-py-class-attr *, .cm-sql-type, .cm-sql-type *": {
    color: "var(--syntax-class)",
  },
  // Função reconhecida em import (Python) e função SQL (lista conhecida ou nome seguido de `(`).
  ".cm-py-function, .cm-py-function *, .cm-sql-function, .cm-sql-function *": { color: "var(--syntax-function)" },
  // Função/tipo SQL que o lang-sql etiqueta como `Keyword` (COUNT, CAST, MAP): sem o negrito da
  // keyword, real ou sintético (a regra do tema, com o escopo do editor, vence a classe da tag).
  ".cm-sql-function, .cm-sql-function *, .cm-sql-type, .cm-sql-type *": { fontWeight: "400", fontSynthesis: "none" },
  // Palavra do Spark fora da lista do lang-sql (MERGE, MATCHED…) e método encadeado no início da
  // linha, com o ponto (`.format(`): cor e negrito de keyword.
  ".cm-sql-keyword, .cm-sql-keyword *, .cm-py-chain, .cm-py-chain *": {
    color: "var(--syntax-keyword)",
    fontWeight: "700",
  },
  // Identificador entre crases/aspas (`QuotedIdentifier`, tag `special(string)`): neutro, não string.
  ".cm-sql-ident, .cm-sql-ident *": { color: "var(--syntax-variable)" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--font-code)",
    lineHeight: "var(--line-height-code)",
    overflow: "auto",
  },
  ".cm-content": {
    fontFamily: "var(--font-code)",
    padding: "0",
    caretColor: "transparent",
    color: "var(--syntax-text, var(--color-text))",
  },
  // Sem gutter (o editor não usa números de linha) e linha ativa sem fundo próprio.
  ".cm-activeLine": { backgroundColor: "transparent" },
  ".cm-line": { padding: "0" },
  ".cm-dropCursor": { borderLeftColor: "var(--color-text)" },
  // Cursor de bloco (1ch) desenhado pelo `drawSelection`; translúcido porque a
  // camada fica acima do texto e o caractere sob o bloco precisa continuar legível.
  ".cm-cursor": {
    borderLeft: "none",
    marginLeft: "0",
    width: "1ch",
    backgroundColor: "var(--color-text)",
    opacity: "0.4",
  },
  // Com `drawSelection` a camada de seleção também pinta sem foco; só o editor
  // focado usa o token. `EditorView.theme` só aceita `&` (os escopos claro/escuro
  // existem apenas em `baseTheme`); a especificidade iguala a do tema base e
  // este tema, montado depois, vence.
  "& .cm-selectionBackground": { background: "transparent" },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground": {
    background: "var(--color-editor-selection)",
  },
  ".cm-placeholder": { color: "var(--color-text-subtle)", fontStyle: "normal" },
  "&.cm-focused .cm-matchingBracket": {
    backgroundColor: "var(--color-accent-subtle)",
    outline: "1px solid var(--color-focus-ring)",
  },
  "&.cm-focused .cm-nonmatchingBracket": { backgroundColor: "var(--color-danger-subtle)" },
});

/*
 * Papéis por tag do Lezer (a regra de uma tag vale para as sub-tags sem regra própria):
 * keyword = palavra reservada (Python: control/operator/definition/moduleKeyword e `async`, ver
 * `pythonNotebook`; SQL: `Keyword`), em negrito sintético porque a VT323 só tem o peso 400
 * (`font-synthesis` liberado no editor em global.css). Operador e pontuação = texto base; nome
 * em `def` e chamada = function; nome em `class` = type; variável, atributo, coluna e tabela =
 * neutro; `escape` = escape; `meta` (decorator inteiro) = decorator. Classe/tipo reconhecido,
 * método encadeado e papéis SQL vêm de decoração (`pythonRoleHighlight`, `sqlRoleHighlight`).
 * Os modificadores do Lezer são normalizados: a ordem function/definition não importa.
 */
const highlight = HighlightStyle.define([
  { tag: t.keyword, color: "var(--syntax-keyword)", fontWeight: "700" },
  { tag: [t.null, t.bool], color: "var(--syntax-constant)" },
  // Sem regra para `special(string)`: f-string (Python) cai na de `string`; o `QuotedIdentifier`
  // do SQL (mesma tag) fica neutro por decoração (`.cm-sql-ident`).
  { tag: [t.string, t.regexp], color: "var(--syntax-string)" },
  // `--syntax-escape` só existe nas células de código; fora delas a cor é herdada.
  { tag: t.escape, color: "var(--syntax-escape)" },
  { tag: [t.number, t.integer, t.float], color: "var(--syntax-number)" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "var(--syntax-comment)", fontFamily: "var(--font-code)" },
  {
    tag: [t.function(t.variableName), t.function(t.propertyName), t.function(t.definition(t.variableName)), t.standard(t.name)],
    color: "var(--syntax-function)",
  },
  { tag: [t.className, t.definition(t.className), t.typeName], color: "var(--syntax-class)" },
  { tag: [t.operator, t.punctuation, t.bracket], color: "var(--syntax-punctuation)" },
  { tag: [t.meta, t.annotation, t.processingInstruction], color: "var(--syntax-meta)" },
  // Tags mais específicas (function/standard…) têm regra própria e vencem esta.
  { tag: [t.variableName, t.name, t.propertyName], color: "var(--syntax-variable)" },
  // markdown
  {
    tag: t.heading,
    color: "var(--syntax-heading)",
    fontFamily: "var(--font-sans)",
  },
  { tag: t.strong, fontFamily: "var(--font-sans)" },
  { tag: t.emphasis, fontFamily: "var(--font-sans)" },
  { tag: t.strikethrough, textDecoration: "line-through" },
  { tag: [t.link, t.url], color: "var(--syntax-link)" },
  { tag: t.monospace, color: "var(--syntax-string)", fontFamily: "var(--font-code)" },
  { tag: t.quote, color: "var(--syntax-comment)" },
  { tag: t.contentSeparator, color: "var(--syntax-punctuation)" },
  { tag: t.invalid, color: "var(--color-danger)" },
]);

export const notebookEditorTheme: Extension = [theme, syntaxHighlighting(highlight)];

/**
 * Python com ajustes de tags sobre o `@lezer/python`, aplicados por `styleTags` no parser
 * (regras novas vencem as do pacote de mesma profundidade):
 * - `return` sai de `controlKeyword` para `keyword` e `async` sai de `modifier` para `keyword`.
 * - `*`/`**` e `FormatConversion FormatSpec` saem de `modifier` para `operator`/`special(string)`.
 * - Em `Decorator { At dottedName ArgList? }` o `dottedName` é regra inline, então os
 *   `VariableName` e `.` são filhos diretos de `Decorator` e recebem `meta`, como o `@`.
 *   O `ArgList` (e o que há dentro dele) mantém as tags normais.
 * Mesmo `data` do `pythonLanguage`: indentação, folding e autocomplete são preservados.
 */
const pythonNotebook = new LanguageSupport(
  pythonLanguage.configure({
    props: [
      styleTags({
        "ReturnStatement/return": t.keyword,
        async: t.keyword,
        '"*" "**"': t.operator,
        "FormatConversion FormatSpec": t.special(t.string),
        "Decorator/VariableName": t.meta,
        'Decorator/"."': t.meta,
      }),
    ],
  }),
  python().support,
);

/** Instância única: todas as células Python compartilham a mesma linguagem configurada. */
export function pythonNotebookLanguage(): LanguageSupport {
  return pythonNotebook;
}

/** Célula markdown: o corpo usa a fonte de conteúdo; `tags.monospace` (código) volta a `--font-code`. */
export const markdownEditorTheme: Extension = Prec.high(
  EditorView.theme({
    ".cm-scroller": { fontFamily: "var(--font-content)" },
    ".cm-content": { fontFamily: "var(--font-content)" },
  }),
);

/** Nó Lezer, tipado via `syntaxTree` (`@lezer/common` não é dependência direta). */
type SyntaxNode = ReturnType<ReturnType<typeof syntaxTree>["resolveInner"]>;
type MarkSink = (from: number, to: number, mark: Decoration) => void;
type VisibleRanges = readonly { from: number; to: number }[];

/**
 * Marcas em qualquer ordem (o `Decoration.set` ordena), sem repetir o nó que atravessa dois
 * intervalos visíveis.
 */
function collectMarks(fill: (add: MarkSink) => void): DecorationSet {
  const seen = new Set<string>();
  const ranges: Range<Decoration>[] = [];
  fill((from, to, mark) => {
    const key = `${from}:${to}`;
    if (from >= to || seen.has(key)) return;
    seen.add(key);
    ranges.push(mark.range(from, to));
  });
  return Decoration.set(ranges, true);
}

/** Plugin que recalcula as marcas de papel quando o documento, a viewport ou a árvore mudam. */
function rolePlugin(roles: (state: EditorState, ranges: VisibleRanges, add: MarkSink) => void): Extension {
  const build = (view: EditorView) => collectMarks((add) => roles(view.state, view.visibleRanges, add));
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = build(view);
      }
      update(u: ViewUpdate) {
        if (u.docChanged || u.viewportChanged || syntaxTree(u.startState) !== syntaxTree(u.state)) {
          this.decorations = build(u.view);
        }
      }
    },
    { decorations: (v) => v.decorations },
  );
}

const sqlFunctionMark = Decoration.mark({ class: "cm-sql-function" });
const sqlTypeMark = Decoration.mark({ class: "cm-sql-type" });
const sqlKeywordMark = Decoration.mark({ class: "cm-sql-keyword" });
const sqlIdentMark = Decoration.mark({ class: "cm-sql-ident" });
/**
 * Tipos do Spark que o StandardSQL do lang-sql não lista em `types` (lá eles viriam como
 * `Identifier`, ou `Keyword` no caso de MAP). Definir `types` no dialeto não basta: sem
 * `keywords` o `SQLDialect.define` ignora `types`, e a lista padrão de keywords não é exportada.
 * São tipo só sem `(` seguinte: `struct(a, b)` e `map(1, 2)` são chamadas (`SQL_CALL_FUNCTIONS`).
 */
const SPARK_EXTRA_TYPES = new Set(["bigint", "tinyint", "string", "long", "short", "byte", "struct", "map"]);
/**
 * Palavras do Spark/Delta que o StandardSQL não lista em `keywords` (chegam como `Identifier`) e
 * que não servem de nome de coluna/tabela na prática: sempre keyword.
 */
const SPARK_EXTRA_KEYWORDS = new Set(["merge", "options", "overwrite", "partitioned", "serdeproperties", "tblproperties", "zorder"]);
/**
 * Palavras de cláusula do Spark que chegam como `Identifier`: sempre keyword, nunca função
 * (`PIVOT (`, `OVER (`, `TABLESAMPLE (`).
 */
const SPARK_CLAUSE_KEYWORDS = new Set([
  "pivot",
  "unpivot",
  "qualify",
  "window",
  "semi",
  "anti",
  "lateral",
  "tablesample",
  "over",
  "partition",
]);
/**
 * Palavras de cláusula do Spark/Delta que também são nomes comuns de coluna (`SELECT version,
 * operation` do DESCRIBE HISTORY): só viram keyword no contexto (ver `contextKeyword`) —
 * `CLUSTER BY`/`DISTRIBUTE BY`/`SORT BY` seguidas de BY. `VERSION AS OF` e `RETAIN 168 HOURS`
 * têm regra própria. `TIMESTAMP` fica de fora: no lang-sql já é tipo (`TIMESTAMP AS OF` sai com
 * a cor de tipo).
 */
const SPARK_BY_CLAUSES = /^(cluster|distribute|sort)$/i;
/**
 * Palavras do Spark/Delta que também são nomes comuns (`SELECT location, delta`): só viram
 * keyword no contexto (ver `contextKeyword`); fora dele ficam neutras.
 */
const SPARK_FORMATS = /^(delta|parquet)$/i;
/** Statements do Delta: `OPTIMIZE t`, `VACUUM t`. */
const DELTA_STATEMENT = /^(optimize|vacuum)$/i;
/** Statements de DDL em que o nome após `USING` é o formato (`CREATE TABLE t USING csv`). */
const DDL_STATEMENT = /^(create|replace)$/i;
/**
 * Funções SQL/Spark invocáveis sem parênteses (`SELECT current_date`): cor de função com ou sem
 * `(`. No StandardSQL chegam como `Keyword`.
 */
const SQL_FUNCTIONS = new Set([
  "current_date",
  "current_timestamp",
]);
/**
 * Funções SQL/Spark que exigem `(`: cor de função só seguidas de `(`, venham como `Identifier` ou
 * como `Keyword` do StandardSQL (COUNT, CAST, MAP). Sem `(` o nome é coluna, cláusula, unidade ou
 * tipo (`SELECT lead`, `LEFT JOIN`, `INTERVAL 1 DAY`, `map<string, int>`) e não recebe esta cor.
 */
const SQL_CALL_FUNCTIONS = new Set([
  // agregação
  "count",
  "sum",
  "avg",
  "min",
  "max",
  "collect_list",
  "collect_set",
  "approx_count_distinct",
  "percentile_approx",
  "stddev",
  "stddev_pop",
  "stddev_samp",
  "variance",
  "var_pop",
  "var_samp",
  // janela
  "row_number",
  "rank",
  "dense_rank",
  "percent_rank",
  "cume_dist",
  "ntile",
  "lag",
  "lead",
  "first",
  "last",
  "first_value",
  "last_value",
  "nth_value",
  // condicional e conversão
  "if",
  "coalesce",
  "nullif",
  "nvl",
  "nvl2",
  "ifnull",
  "greatest",
  "least",
  "cast",
  "try_cast",
  // texto
  "concat",
  "concat_ws",
  "substring",
  "substr",
  "upper",
  "lower",
  "trim",
  "ltrim",
  "rtrim",
  "lpad",
  "rpad",
  "initcap",
  "left",
  "right",
  "replace",
  "position",
  "length",
  "split",
  "regexp_replace",
  "regexp_extract",
  "format_string",
  "format_number",
  // data e hora
  "now",
  "date_add",
  "date_sub",
  "datediff",
  "date_format",
  "date_trunc",
  "to_date",
  "to_timestamp",
  "unix_timestamp",
  "from_unixtime",
  "months_between",
  "add_months",
  "extract",
  "year",
  "month",
  "day",
  "hour",
  "minute",
  "second",
  // matemática
  "mod",
  "abs",
  "round",
  "floor",
  "ceil",
  "ceiling",
  "sqrt",
  "pow",
  "power",
  "exp",
  "ln",
  "log",
  // coleções, JSON e diversos
  "struct",
  "map",
  "size",
  "explode",
  "explode_outer",
  "posexplode",
  "array_contains",
  "element_at",
  "from_json",
  "to_json",
  "get_json_object",
  "hash",
  "md5",
  "sha2",
  "uuid",
  "monotonically_increasing_id",
  "input_file_name",
]);
/**
 * Palavras após as quais `nome (` abre lista de colunas, não chamada: `INSERT INTO t (`,
 * `WITH c (x) AS`, `WITH RECURSIVE r (n) AS`, alias com colunas (`VALUES (1) AS v(a)`).
 */
const NAME_BEFORE_COLUMNS = /^(table|into|view|exists|with|recursive|as)$/i;
/** Keywords que continuam a lista de CTEs (`WITH RECURSIVE a AS (…)`); outra no mesmo nível a encerra. */
const CTE_LIST_KEYWORDS = /^(as|recursive)$/i;
/** Keywords após as quais vem o nome de uma CTE (a `,` entre CTEs também). */
const CTE_NAME_AFTER = /^(with|recursive)$/i;

function isSqlFunction(word: string, call: boolean): boolean {
  return SQL_FUNCTIONS.has(word) || (call && SQL_CALL_FUNCTIONS.has(word));
}

/** Tokens do statement em ordem, achatando parênteses; comentários ficam de fora. */
function statementTokens(node: SyntaxNode, out: SyntaxNode[]): SyntaxNode[] {
  for (let c = node.firstChild; c; c = c.nextSibling) {
    if (c.name === "LineComment" || c.name === "BlockComment") continue;
    if (c.name !== "CompositeIdentifier" && c.firstChild) statementTokens(c, out);
    else out.push(c);
  }
  return out;
}

/** Texto do token sem aspas e em minúsculas. */
function bareName(doc: Text, node: SyntaxNode): string {
  return doc.sliceString(node.from, node.to).replace(/^[`"]|[`"]$/g, "").toLowerCase();
}

function isKeyword(doc: Text, node: SyntaxNode | undefined, pattern: RegExp): boolean {
  return node?.name === "Keyword" && pattern.test(doc.sliceString(node.from, node.to));
}

/**
 * `Identifier` do índice `i` que deve sair com a cor de keyword: palavras do Spark inequívocas e
 * de cláusula sempre; as ambíguas só no contexto — `MATCHED` após WHEN/NOT, `LOCATION` seguido de
 * string, `DELTA`/`PARQUET` após USING/TO (formato), `OPTIMIZE`/`VACUUM` abrindo o statement,
 * `CLUSTER`/`DISTRIBUTE`/`SORT` seguidas de BY, `VERSION` seguida de AS OF e `RETAIN` seguida
 * de número (`VACUUM t RETAIN 168 HOURS`).
 */
function contextKeyword(doc: Text, tokens: SyntaxNode[], i: number): boolean {
  const tok = tokens[i];
  if (tok?.name !== "Identifier") return false;
  const word = bareName(doc, tok);
  if (SPARK_EXTRA_KEYWORDS.has(word) || SPARK_CLAUSE_KEYWORDS.has(word)) return true;
  const prev = tokens[i - 1];
  const next = tokens[i + 1];
  if (SPARK_BY_CLAUSES.test(word)) return next !== undefined && bareName(doc, next) === "by";
  if (word === "version") {
    const after = tokens[i + 2];
    return next !== undefined && after !== undefined && bareName(doc, next) === "as" && bareName(doc, after) === "of";
  }
  if (word === "retain") return next?.name === "Number";
  if (word === "matched") return isKeyword(doc, prev, /^(when|not)$/i);
  if (word === "location") return next?.name === "String";
  if (SPARK_FORMATS.test(word)) return isKeyword(doc, prev, /^(using|to)$/i);
  return i === 0 && DELTA_STATEMENT.test(word);
}

/**
 * Índices dos nomes seguidos de lista de colunas, não de chamada: após `NAME_BEFORE_COLUMNS` e
 * após a `,` que separa CTEs (`WITH a AS (…), b (x) AS (…)`). A lista de CTEs vale no nível de
 * parênteses do WITH até a primeira keyword que não a continua (o SELECT principal) ou até o
 * `)` que fecha esse nível; um WITH aninhado abre a própria lista. Keyword em posição de nome de
 * CTE (após `WITH`, `RECURSIVE` ou a `,` do nível) é o nome, não encerra a lista
 * (`WITH a AS (…), result AS (…), b (x) AS (…)`).
 */
function columnListNames(doc: Text, tokens: SyntaxNode[]): Set<number> {
  const names = new Set<number>();
  const cteLevels: number[] = [];
  let depth = 0;
  tokens.forEach((tok, i) => {
    const prev = tokens[i - 1];
    const comma = prev?.name === "Punctuation" && doc.sliceString(prev.from, prev.to) === ",";
    const cteName = cteLevels.at(-1) === depth && (comma || isKeyword(doc, prev, CTE_NAME_AFTER));
    if (tok.name === "(") depth++;
    else if (tok.name === ")") {
      depth--;
      while ((cteLevels.at(-1) ?? -1) > depth) cteLevels.pop();
    } else if (isKeyword(doc, tok, /^with$/i)) cteLevels.push(depth);
    else if (tok.name === "Keyword" && !cteName && cteLevels.at(-1) === depth && !CTE_LIST_KEYWORDS.test(bareName(doc, tok))) {
      cteLevels.pop();
    }
    if (tokens[i + 1]?.name !== "(") return;
    if (cteName || isKeyword(doc, prev, NAME_BEFORE_COLUMNS)) names.add(i);
  });
  return names;
}

/**
 * Papéis SQL por statement. Tabela, alias, coluna e qualificador ficam neutros (tag `name`).
 * "Chamada" = nome seguido de `(` fora de posição de lista de colunas (ver `columnListNames`).
 * - `Keyword`: MAP sem `(` = tipo; função reconhecida (COUNT, CAST, MAP…) = função se chamada,
 *   e as invocáveis sem parênteses (CURRENT_DATE) sempre.
 * - `Identifier`: palavra do Spark/Delta fora da lista do lang-sql = keyword (as ambíguas só no
 *   contexto, ver `contextKeyword`), assim como o formato após `USING` no DDL (`USING csv`);
 *   tipo do Spark fora da lista sem `(` = tipo (`struct<…>`); chamada ou função invocável sem
 *   parênteses = função.
 * - `QuotedIdentifier` (`` `col` ``, solto ou segmento de `a.b`), cuja tag é `special(string)`,
 *   recebe a marca neutra para não sair com a cor de string.
 * NULL/TRUE/FALSE já chegam como `Null`/`Bool` (cor de constante pela tag).
 */
function sqlStatementRoles(statement: SyntaxNode, doc: Text, add: MarkSink): void {
  const tokens = statementTokens(statement, []);
  const isDdl = tokens[0] !== undefined && DDL_STATEMENT.test(bareName(doc, tokens[0]));
  const columnNames = columnListNames(doc, tokens);
  tokens.forEach((tok, i) => {
    const prev = tokens[i - 1];
    const callNext = tokens[i + 1]?.name === "(";
    const call = callNext && !columnNames.has(i);
    switch (tok.name) {
      case "Keyword": {
        const word = bareName(doc, tok);
        if (SPARK_EXTRA_TYPES.has(word) && !callNext) add(tok.from, tok.to, sqlTypeMark);
        else if (isSqlFunction(word, call)) add(tok.from, tok.to, sqlFunctionMark);
        return;
      }
      case "QuotedIdentifier":
        add(tok.from, tok.to, sqlIdentMark);
        return;
      case "CompositeIdentifier":
        for (let c = tok.firstChild; c; c = c.nextSibling) {
          if (c.name === "QuotedIdentifier") add(c.from, c.to, sqlIdentMark);
        }
        return;
      case "Identifier": {
        const word = bareName(doc, tok);
        if ((isDdl && isKeyword(doc, prev, /^using$/i)) || contextKeyword(doc, tokens, i)) {
          add(tok.from, tok.to, sqlKeywordMark);
        } else if (SPARK_EXTRA_TYPES.has(word) && !callNext) {
          add(tok.from, tok.to, sqlTypeMark);
        } else if (call || SQL_FUNCTIONS.has(word)) {
          add(tok.from, tok.to, sqlFunctionMark);
        }
      }
    }
  });
}

function sqlRoles(state: EditorState, ranges: VisibleRanges, add: MarkSink): void {
  const doc = state.doc;
  for (const { from, to } of ranges) {
    syntaxTree(state).iterate({
      from,
      to,
      enter: (node) => {
        if (node.name !== "Statement") return;
        sqlStatementRoles(node.node, doc, add);
        return false;
      },
    });
  }
}

/**
 * Papéis SQL que o lang-sql não distingue (função, tipo e palavra do Spark, identificador entre
 * aspas). Registrar somente na linguagem SQL (ver `CodeEditor.languageExtension`).
 */
export const sqlRoleHighlight: Extension = rolePlugin(sqlRoles);

const pyClassMark = Decoration.mark({ class: "cm-py-class" });
const pyClassAttrMark = Decoration.mark({ class: "cm-py-class-attr" });
const pyFunctionMark = Decoration.mark({ class: "cm-py-function" });
const pyChainMark = Decoration.mark({ class: "cm-py-chain" });
/**
 * Classes e tipos reconhecidos pelo nome (cor de type, em referência ou chamada). Sem heurística
 * por maiúscula: nome fora da lista fica neutro. Nomes que também são módulos (`datetime`) ficam
 * de fora.
 */
const PY_KNOWN_CLASSES = new Set([
  // builtins
  "int",
  "float",
  "complex",
  "str",
  "bytes",
  "bytearray",
  "bool",
  "list",
  "dict",
  "set",
  "frozenset",
  "tuple",
  "object",
  "type",
  "Exception",
  "BaseException",
  "ValueError",
  "TypeError",
  "KeyError",
  "IndexError",
  "RuntimeError",
  "AttributeError",
  "NotImplementedError",
  // typing, decimal, pathlib, datetime
  "Any",
  "Optional",
  "Union",
  "List",
  "Dict",
  "Tuple",
  "Callable",
  "Iterable",
  "Iterator",
  "Decimal",
  "Path",
  "timedelta",
  // AWS Glue
  "GlueContext",
  "DynamicFrame",
  "DynamicFrameCollection",
  "Job",
  // PySpark
  "SparkContext",
  "SparkConf",
  "SparkSession",
  "SQLContext",
  "HiveContext",
  "DataFrame",
  "DataFrameReader",
  "DataFrameWriter",
  "GroupedData",
  "Column",
  "Row",
  "Window",
  "WindowSpec",
  "StorageLevel",
  "RDD",
  "DeltaTable",
  // pyspark.sql.types
  "DataType",
  "StructType",
  "StructField",
  "StringType",
  "VarcharType",
  "CharType",
  "BinaryType",
  "BooleanType",
  "ByteType",
  "ShortType",
  "IntegerType",
  "LongType",
  "FloatType",
  "DoubleType",
  "DecimalType",
  "DateType",
  "TimestampType",
  "TimestampNTZType",
  "ArrayType",
  "MapType",
  "NullType",
  // DuckDB
  "DuckDBPyConnection",
  "DuckDBPyRelation",
]);
/** Funções reconhecidas quando importadas por nome (`from pyspark.sql.functions import col`). */
const PY_KNOWN_FUNCTIONS = new Set([
  "print",
  "len",
  "range",
  "col",
  "lit",
  "when",
  "expr",
  "udf",
  "broadcast",
  "current_timestamp",
  "current_date",
  "to_date",
  "to_timestamp",
  "concat",
  "concat_ws",
  "coalesce",
  "explode",
  "row_number",
  "getResolvedOptions",
]);
/** Pais em que o `VariableName` já tem papel próprio: definição e decorator. */
const PY_OWN_ROLE_PARENT = new Set(["ClassDefinition", "FunctionDefinition", "Decorator"]);

/**
 * `ImportStatement` do `@lezer/python` é plano (`dottedName`/`importedNames` são regras inline).
 * Caminho de módulo, `import a.b` e aliases ficam neutros; só os nomes após `import` em
 * `from m import X, y` recebem type/function, e só quando reconhecidos.
 */
function importRoles(node: SyntaxNode, doc: Text, add: MarkSink): void {
  if (node.firstChild?.name !== "from") return;
  let names = false;
  let alias = false;
  for (let c: SyntaxNode | null = node.firstChild; c; c = c.nextSibling) {
    if (c.name === "import") names = true;
    else if (c.name === "as") alias = true;
    else if (c.name === ",") alias = false;
    else if (c.name === "VariableName" && names && !alias) {
      const name = doc.sliceString(c.from, c.to);
      if (PY_KNOWN_CLASSES.has(name)) add(c.from, c.to, pyClassMark);
      else if (PY_KNOWN_FUNCTIONS.has(name)) add(c.from, c.to, pyFunctionMark);
    }
  }
}

/** `pos` é o primeiro caractere não branco da linha. */
function startsLine(doc: Text, pos: number): boolean {
  const line = doc.lineAt(pos);
  return doc.sliceString(line.from, pos).trim() === "";
}

/**
 * `obj.nome`: chamado (`obj.nome(`) com o `.` abrindo a linha = método encadeado (ponto e nome
 * com cor e negrito de keyword); os demais chamados mantêm a cor de função pela tag. Não chamado,
 * com `obj` classe reconhecida (`SparkSession.builder`) = atributo de classe (cor de type); os
 * demais atributos ficam neutros.
 */
function memberRoles(member: SyntaxNode, doc: Text, add: MarkSink): void {
  const prop = member.lastChild;
  if (prop?.name !== "PropertyName") return;
  if (member.parent?.name === "CallExpression") {
    const dot = prop.prevSibling;
    if (dot?.name === "." && startsLine(doc, dot.from)) add(dot.from, prop.to, pyChainMark);
    return;
  }
  const obj = member.firstChild;
  if (obj?.name === "VariableName" && PY_KNOWN_CLASSES.has(doc.sliceString(obj.from, obj.to))) {
    add(prop.from, prop.to, pyClassAttrMark);
  }
}

/**
 * Papéis Python que a árvore não expõe por tag: classe/tipo reconhecido (fora de definição e
 * decorator), símbolo reconhecido em `from … import`, método encadeado no início da linha e
 * atributo de classe reconhecida. Os demais papéis vêm das tags no `HighlightStyle`.
 */
function pythonRoles(state: EditorState, ranges: VisibleRanges, add: MarkSink): void {
  const doc = state.doc;
  for (const { from, to } of ranges) {
    syntaxTree(state).iterate({
      from,
      to,
      enter: (node) => {
        switch (node.name) {
          case "ImportStatement":
            importRoles(node.node, doc, add);
            return false;
          case "MemberExpression":
            memberRoles(node.node, doc, add);
            return;
          case "VariableName": {
            const parent = node.node.parent;
            if (parent && PY_OWN_ROLE_PARENT.has(parent.name)) return;
            if (PY_KNOWN_CLASSES.has(doc.sliceString(node.from, node.to))) add(node.from, node.to, pyClassMark);
          }
        }
      },
    });
  }
}

/** Registrar somente na linguagem Python (ver `CodeEditor.languageExtension`). */
export const pythonRoleHighlight: Extension = rolePlugin(pythonRoles);
