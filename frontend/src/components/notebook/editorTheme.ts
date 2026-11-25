/**
 * Tema do CodeMirror 6 integrado aos tokens do app. Todas as cores são
 * `var(--...)`, então a troca claro/escuro (data-theme / prefers-color-scheme)
 * se aplica sem reconfigurar o editor. As cores de sintaxe (`--syntax-*`) são
 * definidas em `Notebook.module.css`, no contêiner do notebook.
 */
import { python, pythonLanguage } from "@codemirror/lang-python";
import { HighlightStyle, LanguageSupport, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate } from "@codemirror/view";
import { type EditorState, type Extension, Prec, RangeSetBuilder, type Text } from "@codemirror/state";
import { styleTags, tags as t } from "@lezer/highlight";

const theme = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    color: "var(--color-text)",
    fontSize: "13.5px",
  },
  // O `*` vence o span de `special(string)` do QuotedIdentifier, aninhado ou não.
  // Qualificador SQL usa o papel de módulo; nome de tabela, o de atributo.
  ".cm-sql-qualifier, .cm-sql-qualifier *": { color: "var(--syntax-module)" },
  // Nome de tabela: segmento final de `schema.tabela` ou nome após FROM/JOIN/INTO/TABLE…
  ".cm-sql-table, .cm-sql-table *": { color: "var(--syntax-attribute)" },
  // Alias de tabela (`FROM bronze.vendas v`) e seu uso como prefixo de coluna (`v.id`).
  ".cm-sql-alias, .cm-sql-alias *": { color: "var(--syntax-alias)" },
  // Função SQL: identificador seguido de `(` (o dialeto Spark não declara builtins).
  ".cm-sql-function, .cm-sql-function *": { color: "var(--syntax-function)" },
  // Tipo do Spark fora da lista do lang-sql (BIGINT, STRING…): mesma cor de `typeName`.
  ".cm-sql-type, .cm-sql-type *": { color: "var(--syntax-class)" },
  // Palavra do Spark fora da lista do lang-sql (MERGE, MATCHED, DELTA…): cor de keyword.
  ".cm-sql-keyword, .cm-sql-keyword *": { color: "var(--syntax-keyword)" },
  // Python (ver `pythonRoleHighlight`): classe por heurística, classe chamada e caminho de módulo em import.
  ".cm-py-class, .cm-py-class *": { color: "var(--syntax-class)" },
  ".cm-py-class-call, .cm-py-class-call *": { color: "var(--syntax-class-call)" },
  ".cm-py-module, .cm-py-module *": { color: "var(--syntax-module)" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--font-code)",
    lineHeight: "var(--line-height-code)",
    overflow: "auto",
  },
  ".cm-content": {
    fontFamily: "var(--font-code)",
    fontWeight: "400",
    // Sobrescreve o antialiased global só no código: traço mais encorpado no macOS.
    WebkitFontSmoothing: "auto",
    MozOsxFontSmoothing: "auto",
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
 * Papéis por tag do Lezer. Python (`@lezer/python`): `controlKeyword` = if/for/return…;
 * `operatorKeyword` = in/not/and/or/is/del; `definitionOperator` = `=`; `updateOperator`
 * = `+=`…; `compareOperator` = `==`/`<`…; nome em `def` = function(definition(variableName));
 * nome em `class` = definition(className); chamada = function(variableName); `@` = meta.
 * Ajustes do notebook sobre o Python (ver `pythonNotebookLanguage`): `return` = keyword
 * e o nome do decorator (`@F.udf`) inteiro = meta.
 * Papéis de identificador: `variableName` (Python) e `name` (identificador SQL) = variável; `propertyName`
 * fora de chamada = atributo; `typeName` (tipo SQL) = classe. Classe Python (referência ou
 * chamada) e módulo em import vêm de decoração (`pythonRoleHighlight`); qualificador,
 * tabela, alias, função e palavras do Spark no SQL, de `sqlQualifierHighlight`.
 * Os modificadores do Lezer são normalizados, então a ordem function/definition não importa.
 */
const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.moduleKeyword], color: "var(--syntax-keyword)" },
  { tag: [t.definitionKeyword, t.self], color: "var(--syntax-keyword)" },
  { tag: t.controlKeyword, color: "var(--syntax-control)" },
  { tag: t.compareOperator, color: "var(--syntax-compare)" },
  { tag: [t.definitionOperator, t.updateOperator, t.operatorKeyword], color: "var(--syntax-assign)" },
  { tag: [t.null, t.bool], color: "var(--syntax-constant)" },
  { tag: [t.string, t.special(t.string), t.regexp], color: "var(--syntax-string)" },
  { tag: [t.number, t.integer, t.float], color: "var(--syntax-number)" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "var(--syntax-comment)", fontFamily: "var(--font-code)" },
  { tag: [t.function(t.variableName), t.function(t.propertyName), t.standard(t.name)], color: "var(--syntax-function)" },
  {
    tag: [t.definition(t.variableName), t.definition(t.function(t.variableName)), t.definition(t.className)],
    color: "var(--syntax-definition)",
  },
  { tag: [t.className, t.typeName], color: "var(--syntax-class)" },
  { tag: t.namespace, color: "var(--syntax-module)" },
  { tag: [t.operator, t.punctuation, t.bracket], color: "var(--syntax-punctuation)" },
  { tag: [t.meta, t.annotation, t.processingInstruction], color: "var(--syntax-meta)" },
  { tag: t.propertyName, color: "var(--syntax-attribute)" },
  // Tags mais específicas (function/definition/standard…) têm regra própria e vencem esta.
  { tag: [t.variableName, t.name], color: "var(--syntax-variable)" },
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
 * Python com dois ajustes de tags sobre o `@lezer/python`, aplicados por `styleTags`
 * no parser (regras com contexto vencem as de profundidade 0 do pacote):
 * - `return` sai de `controlKeyword` (rosa) para `keyword` (cor de keyword); os demais
 *   `controlKeyword` (if/for/while/break/continue/pass/yield/try/except/with/raise…) não mudam.
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

const qualifierMark = Decoration.mark({ class: "cm-sql-qualifier" });
const tableMark = Decoration.mark({ class: "cm-sql-table" });
const aliasMark = Decoration.mark({ class: "cm-sql-alias" });
const functionMark = Decoration.mark({ class: "cm-sql-function" });
const sqlTypeMark = Decoration.mark({ class: "cm-sql-type" });
const sqlKeywordMark = Decoration.mark({ class: "cm-sql-keyword" });
/**
 * Tipos do Spark que o StandardSQL do lang-sql não lista em `types` (lá eles viriam como
 * `Identifier`). Definir `types` no dialeto não basta: sem `keywords` o `SQLDialect.define`
 * ignora `types`, e a lista padrão de keywords não é exportada.
 */
const SPARK_EXTRA_TYPES = new Set(["bigint", "tinyint", "string", "long", "short", "byte"]);
/**
 * Palavras do Spark/Delta que o StandardSQL não lista em `keywords` (chegam como `Identifier`) e
 * que não servem de nome de coluna/tabela na prática: sempre keyword.
 */
const SPARK_EXTRA_KEYWORDS = new Set(["merge", "overwrite", "partitioned", "tblproperties", "zorder"]);
/**
 * Palavras de cláusula do Spark que chegam como `Identifier`: sempre keyword, nunca relação,
 * alias ou função (`PIVOT (`, `OVER (`, `TABLESAMPLE (`).
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
 * Palavras do Spark/Delta que também são nomes comuns (`SELECT location, delta`): só viram
 * keyword no contexto (ver `contextKeyword`); fora dele seguem o papel de identificador.
 */
const SPARK_FORMATS = /^(delta|parquet)$/i;
/** Statements do Delta cujo nome seguinte é a tabela: `OPTIMIZE t`, `VACUUM t`. */
const DELTA_STATEMENT = /^(optimize|vacuum)$/i;
/** Palavras que fecham a lista de relações do FROM (depois delas, `,` não introduz relação). */
const FROM_CLAUSE_END =
  /^(where|group|having|order|limit|union|intersect|except|on|using|select|set|values|window|qualify|lateral|cluster|distribute|sort)$/i;
/** Funções que o StandardSQL etiqueta como `Keyword` (COUNT…); só viram função seguidas de `(`. */
const SQL_FUNCTION_KEYWORDS = new Set([
  "count",
  "sum",
  "avg",
  "min",
  "max",
  "cast",
  "coalesce",
  "nullif",
  "extract",
  "substring",
  "trim",
  "position",
  "upper",
  "lower",
]);
/** Nó Lezer, tipado via `syntaxTree` (`@lezer/common` não é dependência direta). */
type SyntaxNode = ReturnType<ReturnType<typeof syntaxTree>["resolveInner"]>;
/**
 * Palavras que antecedem nome de tabela/view (`FROM t`, `CREATE TABLE t (`, `INSERT INTO t (`).
 * O nome seguinte é tabela, nunca função, mesmo seguido de `(`.
 * `USING` fica de fora: só introduz relação no MERGE (ver `sqlStatementRoles`); no DDL vem o
 * formato (`USING csv`) e no `JOIN ... USING (cols)` vêm colunas.
 */
const TABLE_INTRODUCER = /^(table|into|view|exists|from|join|update)$/i;
/** Funções cujo `FROM` interno não é de tabela: `EXTRACT(YEAR FROM ts)`, `TRIM(BOTH ' ' FROM s)`. */
const FROM_INSIDE_CALL = /^(extract|trim|substring)$/i;
const SQL_NAME = new Set(["Identifier", "QuotedIdentifier", "CompositeIdentifier"]);

/** Tokens do statement em ordem, achatando parênteses; comentários ficam de fora. */
function statementTokens(node: SyntaxNode, out: SyntaxNode[]): SyntaxNode[] {
  for (let c = node.firstChild; c; c = c.nextSibling) {
    if (c.name === "LineComment" || c.name === "BlockComment") continue;
    if (c.name !== "CompositeIdentifier" && c.firstChild) statementTokens(c, out);
    else out.push(c);
  }
  return out;
}

/** Nome sem aspas e em minúsculas, para comparar tabela/alias com o prefixo de `alias.coluna`. */
function bareName(doc: Text, node: SyntaxNode): string {
  return doc.sliceString(node.from, node.to).replace(/^[`"]|[`"]$/g, "").toLowerCase();
}

function isKeyword(doc: Text, node: SyntaxNode | undefined, pattern: RegExp): boolean {
  return node?.name === "Keyword" && pattern.test(doc.sliceString(node.from, node.to));
}

function isPunct(doc: Text, node: SyntaxNode | undefined, text: string): boolean {
  return node !== undefined && doc.sliceString(node.from, node.to) === text;
}

/**
 * `Identifier` do índice `i` que deve sair com a cor de keyword: palavras do Spark inequívocas e
 * de cláusula sempre; as ambíguas só no contexto — `MATCHED` após WHEN/NOT, `LOCATION` seguido de
 * string, `DELTA`/`PARQUET` após USING/TO (formato), `OPTIMIZE`/`VACUUM` abrindo o statement.
 */
function contextKeyword(doc: Text, tokens: SyntaxNode[], i: number): boolean {
  const tok = tokens[i];
  if (tok?.name !== "Identifier") return false;
  const word = bareName(doc, tok);
  if (SPARK_EXTRA_KEYWORDS.has(word) || SPARK_CLAUSE_KEYWORDS.has(word)) return true;
  const prev = tokens[i - 1];
  if (word === "matched") return isKeyword(doc, prev, /^(when|not)$/i);
  if (word === "location") return tokens[i + 1]?.name === "String";
  if (SPARK_FORMATS.test(word)) return isKeyword(doc, prev, /^(using|to)$/i);
  return i === 0 && DELTA_STATEMENT.test(word);
}

/**
 * Papéis SQL que o lang-sql não distingue (todo identificador é `name`), por statement:
 * - relação: nome após FROM/JOIN/INTO/TABLE/VIEW/EXISTS/UPDATE, após USING só no MERGE, após
 *   `,` na lista do FROM e após OPTIMIZE/VACUUM; o identificador seguinte (direto ou após AS) é
 *   alias de tabela, e o que segue o `)` de uma subquery aberta após FROM/JOIN (ou USING no
 *   MERGE) ou de uma função de tabela (`FROM read_parquet('x') r`) é alias dela; o nome da
 *   função de tabela sai com a cor de função.
 *   `FROM` dentro de EXTRACT/TRIM/SUBSTRING e `LATERAL VIEW` não introduzem relação; o nome após
 *   `USING` fora do MERGE (formato do DDL: `USING csv`) sai com a cor de keyword.
 * - `x.y…` (`CompositeIdentifier`): se `x` é tabela ou alias do statement, `x` = alias e
 *   o resto fica como coluna; senão os segmentos até o último `.` (inclusive) = qualificador
 *   e o último segmento = tabela.
 * - identificador seguido de `(` (fora de relação) e keyword de função (COUNT…) seguida de
 *   `(` = função; tipo do Spark fora da lista do lang-sql = tipo; palavra do Spark/Delta
 *   fora da lista (MERGE, QUALIFY…) = keyword, as ambíguas (LOCATION, DELTA, MATCHED…) só no
 *   contexto (`contextKeyword`).
 * Os demais identificadores ficam com a tag `name` (papel de coluna).
 */
function sqlStatementRoles(statement: SyntaxNode, doc: Text, add: (from: number, to: number, mark: Decoration) => void): void {
  const tokens = statementTokens(statement, []);
  const relation = new Set<number>();
  const alias = new Set<number>();
  const known = new Set<string>();
  const ddlFormat = new Set<number>();
  const isMerge = tokens[0] !== undefined && bareName(doc, tokens[0]) === "merge";
  // `)` que fecha subquery (após FROM/JOIN, ou USING no MERGE) ou função de tabela
  // (`read_parquet('x')`): o nome seguinte é alias dela.
  const subqueryClose = new Set<number>();
  // Função de tabela no FROM/JOIN: o nome sai com a cor de função, não de tabela.
  const tableCall = new Set<number>();
  // Parênteses abertos: `call` = abriu EXTRACT/TRIM/SUBSTRING; `subquery` = subquery ou função de
  // tabela; `fromOpen` = estado da lista de relações do FROM do nível de fora, restaurado no `)`.
  const parens: { call: boolean; subquery: boolean; fromOpen: boolean }[] = [];
  // Lista de relações do FROM aberta no nível atual: `FROM a x, b y` — após `,` vem relação.
  let fromOpen = false;
  tokens.forEach((tok, i) => {
    const prev = tokens[i - 1];
    // EXTRACT/TRIM chegam como `Identifier` ou `Keyword` conforme o dialeto: compara só o texto.
    if (tok.name === "(") {
      const call = prev !== undefined && FROM_INSIDE_CALL.test(bareName(doc, prev));
      // Relação seguida de `(` = função de tabela, exceto após TABLE/INTO/VIEW/EXISTS/UPDATE
      // (`CREATE TABLE t (`, `INSERT INTO t (`), onde o `(` abre colunas.
      const fnTable = relation.has(i - 1) && !isKeyword(doc, tokens[i - 2], /^(table|into|view|exists|update)$/i);
      if (fnTable) {
        relation.delete(i - 1);
        tableCall.add(i - 1);
        known.delete(bareName(doc, prev!.lastChild ?? prev!));
      }
      const subquery = isKeyword(doc, prev, /^(from|join)$/i) || (isMerge && isKeyword(doc, prev, /^using$/i)) || fnTable;
      parens.push({ call, subquery, fromOpen });
      fromOpen = false;
    } else if (tok.name === ")") {
      const closed = parens.pop();
      if (closed?.subquery) subqueryClose.add(i);
      fromOpen = closed?.fromOpen ?? false;
    }
    const inCall = parens[parens.length - 1]?.call === true;
    if (tok.name === "Keyword" || tok.name === "Identifier") {
      if (isKeyword(doc, tok, /^from$/i) && !inCall) fromOpen = true;
      else if (FROM_CLAUSE_END.test(bareName(doc, tok))) fromOpen = false;
    }
    if (!SQL_NAME.has(tok.name) || contextKeyword(doc, tokens, i)) return;
    if (isKeyword(doc, prev, /^using$/i) && !isMerge) {
      ddlFormat.add(i);
      return;
    }
    const fromInCall = inCall && isKeyword(doc, prev, /^from$/i);
    // `LATERAL VIEW explode(...)`: o VIEW ali não introduz relação.
    const lateralView = isKeyword(doc, prev, /^view$/i) && tokens[i - 2] !== undefined && bareName(doc, tokens[i - 2]!) === "lateral";
    const introduced =
      (isKeyword(doc, prev, TABLE_INTRODUCER) && !fromInCall && !lateralView) ||
      isKeyword(doc, prev, /^using$/i) ||
      (fromOpen && isPunct(doc, prev, ",")) ||
      (i === 1 && prev !== undefined && DELTA_STATEMENT.test(bareName(doc, prev)));
    if (introduced) {
      relation.add(i);
      known.add(bareName(doc, tok.lastChild ?? tok));
      return;
    }
    if (tok.name === "CompositeIdentifier") return;
    const afterAs = isKeyword(doc, prev, /^as$/i);
    const prevRelation =
      relation.has(i - 1) || subqueryClose.has(i - 1) || (afterAs && (relation.has(i - 2) || subqueryClose.has(i - 2)));
    if (prevRelation) {
      alias.add(i);
      known.add(bareName(doc, tok));
    }
  });
  tokens.forEach((tok, i) => {
    const callNext = tokens[i + 1]?.name === "(";
    if (tok.name === "Keyword") {
      if (callNext && SQL_FUNCTION_KEYWORDS.has(bareName(doc, tok))) add(tok.from, tok.to, functionMark);
      return;
    }
    if (tok.name === "CompositeIdentifier") {
      const head = tok.firstChild;
      const tail = tok.lastChild;
      if (!head || !tail || head === tail) return;
      if (known.has(bareName(doc, head))) {
        add(head.from, head.to, aliasMark);
        return;
      }
      // Inclui o `.` final: o qualificador (`bronze.`) inteiro tem a cor de módulo.
      add(tok.from, tail.from, qualifierMark);
      add(tail.from, tail.to, tableMark);
      return;
    }
    if (tok.name !== "Identifier" && tok.name !== "QuotedIdentifier") return;
    if (ddlFormat.has(i)) add(tok.from, tok.to, sqlKeywordMark);
    else if (alias.has(i)) add(tok.from, tok.to, aliasMark);
    else if (relation.has(i)) add(tok.from, tok.to, tableMark);
    else if (tableCall.has(i)) add(tok.from, tok.to, functionMark);
    else if (contextKeyword(doc, tokens, i)) add(tok.from, tok.to, sqlKeywordMark);
    else if (tok.name === "Identifier" && SPARK_EXTRA_TYPES.has(bareName(doc, tok))) add(tok.from, tok.to, sqlTypeMark);
    else if (tok.name === "Identifier" && callNext) add(tok.from, tok.to, functionMark);
  });
}

function qualifierDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  const doc = view.state.doc;
  let last = -1;
  const add = (from: number, to: number, mark: Decoration) => {
    if (from < last) return; // statement que atravessa dois intervalos visíveis: já emitido
    last = to;
    builder.add(from, to, mark);
  };
  for (const { from, to } of view.visibleRanges) {
    syntaxTree(view.state).iterate({
      from,
      to,
      enter: (node) => {
        if (node.name !== "Statement") return;
        sqlStatementRoles(node.node, doc, add);
        return false;
      },
    });
  }
  return builder.finish();
}

/** Registrar somente na linguagem SQL (ver `CodeEditor.languageExtension`). */
export const sqlQualifierHighlight: Extension = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = qualifierDecorations(view);
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.viewportChanged || syntaxTree(u.startState) !== syntaxTree(u.state)) {
        this.decorations = qualifierDecorations(u.view);
      }
    }
  },
  { decorations: (v) => v.decorations },
);

const pyClassMark = Decoration.mark({ class: "cm-py-class" });
const pyClassCallMark = Decoration.mark({ class: "cm-py-class-call" });
const pyModuleMark = Decoration.mark({ class: "cm-py-module" });
/** Heurística de classe: maiúscula inicial e ao menos uma minúscula (`DataFrame`; não `F` nem `MAX_ROWS`). */
const PY_CLASS_NAME = /^_*[A-Z]\w*[a-z]\w*$/;
/** Pais em que o `VariableName` já tem papel próprio: definição e decorator. */
const PY_OWN_ROLE_PARENT = new Set(["ClassDefinition", "FunctionDefinition", "Decorator"]);
const PY_IMPORT_DOT = new Set([".", "...", "Ellipsis"]);

type PyRole = "class" | "classCall" | "module";
type RoleSink = (from: number, to: number, role: PyRole) => void;

/**
 * `ImportStatement` do `@lezer/python` é plano (`dottedName`/`importedNames` são regras
 * inline), então o papel depende da posição em relação às palavras `from`/`import`/`as`:
 * - `from a.b import X, y as Z`: `a`, `.`, `b` = módulo; `X`/`Z` = classe se CamelCase; `y` = variável.
 * - `import a.b as c, GlueContext`: segmentos e pontos = módulo, exceto CamelCase = classe;
 *   o alias após `as` = classe se CamelCase, senão variável.
 */
function importRoles(node: SyntaxNode, doc: Text, add: RoleSink): void {
  const fromForm = node.firstChild?.name === "from";
  let inPath = true;
  let alias = false;
  for (let c = node.firstChild; c; c = c.nextSibling) {
    switch (c.name) {
      case "from":
        continue;
      case "import":
        inPath = !fromForm;
        continue;
      case "as":
        alias = true;
        continue;
      case ",":
        alias = false;
        continue;
      case "VariableName": {
        const isClass = PY_CLASS_NAME.test(doc.sliceString(c.from, c.to));
        if (alias) {
          if (isClass) add(c.from, c.to, "class");
          alias = false;
        } else if (fromForm && inPath) add(c.from, c.to, "module");
        else if (isClass) add(c.from, c.to, "class");
        else if (!fromForm) add(c.from, c.to, "module");
        continue;
      }
      default:
        if (inPath && !alias && PY_IMPORT_DOT.has(c.name)) add(c.from, c.to, "module");
    }
  }
}

/**
 * Papéis Python que a árvore não expõe por tag: classe (heurística CamelCase, fora de
 * definição/decorator), classe chamada (`GlueContext(`, CamelCase como alvo direto da
 * chamada; demais chamadas mantêm a cor de função) e caminho de módulo em `import`/`from`. Os demais papéis (variável, atributo, chamada)
 * vêm das tags no `HighlightStyle`.
 */
function pythonRoles(state: EditorState, ranges: readonly { from: number; to: number }[], add: RoleSink): void {
  const doc = state.doc;
  let last = -1;
  const sink: RoleSink = (from, to, role) => {
    if (from < last) return; // nó que atravessa dois intervalos visíveis: já emitido
    last = to;
    add(from, to, role);
  };
  for (const { from, to } of ranges) {
    syntaxTree(state).iterate({
      from,
      to,
      enter: (node) => {
        if (node.name === "ImportStatement") {
          importRoles(node.node, doc, sink);
          return false;
        }
        if (node.name !== "VariableName") return;
        const parent = node.node.parent;
        if (parent && PY_OWN_ROLE_PARENT.has(parent.name)) return;
        if (!PY_CLASS_NAME.test(doc.sliceString(node.from, node.to))) return;
        sink(node.from, node.to, parent?.name === "CallExpression" ? "classCall" : "class");
      },
    });
  }
}

function pythonRoleDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  pythonRoles(view.state, view.visibleRanges, (from, to, role) =>
    builder.add(from, to, role === "class" ? pyClassMark : role === "classCall" ? pyClassCallMark : pyModuleMark),
  );
  return builder.finish();
}

/** Registrar somente na linguagem Python (ver `CodeEditor.languageExtension`). */
export const pythonRoleHighlight: Extension = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = pythonRoleDecorations(view);
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.viewportChanged || syntaxTree(u.startState) !== syntaxTree(u.state)) {
        this.decorations = pythonRoleDecorations(u.view);
      }
    }
  },
  { decorations: (v) => v.decorations },
);
