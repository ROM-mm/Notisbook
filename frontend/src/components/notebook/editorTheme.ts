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
  // Nome de tabela: identificador logo após o qualificador (`schema.tabela`).
  ".cm-sql-table, .cm-sql-table *": { color: "var(--syntax-attribute)" },
  // Função SQL: identificador seguido de `(` (o dialeto Spark não declara builtins).
  ".cm-sql-function, .cm-sql-function *": { color: "var(--syntax-function)" },
  // Tipo do Spark fora da lista do lang-sql (BIGINT, STRING…): mesma cor de `typeName`.
  ".cm-sql-type, .cm-sql-type *": { color: "var(--syntax-class)" },
  // Python (ver `pythonRoleHighlight`): classe por heurística e caminho de módulo em import.
  ".cm-py-class, .cm-py-class *": { color: "var(--syntax-class)" },
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
 * fora de chamada = atributo; `typeName` (tipo SQL) = classe. Classe Python e módulo em
 * import vêm de decoração (`pythonRoleHighlight`); qualificador/tabela SQL, de
 * `sqlQualifierHighlight`.
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
const functionMark = Decoration.mark({ class: "cm-sql-function" });
const sqlTypeMark = Decoration.mark({ class: "cm-sql-type" });
/**
 * Tipos do Spark que o StandardSQL do lang-sql não lista em `types` (lá eles viriam como
 * `Identifier`). Definir `types` no dialeto não basta: sem `keywords` o `SQLDialect.define`
 * ignora `types`, e a lista padrão de keywords não é exportada.
 */
const SPARK_EXTRA_TYPES = new Set(["bigint", "tinyint", "string", "long", "short", "byte"]);
const QUALIFIER_TAIL = /^\.[\w"`]/;
/** Termina em `<nome>.`: o identificador seguinte é o último segmento de um nome qualificado. */
const QUALIFIED_HEAD = /[\w"`]\.$/;
const CALL_TAIL = /^\s*\(/;
/** Nó Lezer, tipado via `syntaxTree` (`@lezer/common` não é dependência direta). */
type SyntaxNode = ReturnType<ReturnType<typeof syntaxTree>["resolveInner"]>;
/** Palavras que antecedem nome de tabela/view em DDL/DML (`CREATE TABLE t (`, `INSERT INTO t (`). */
const TABLE_INTRODUCER = /^(table|into|view|exists)$/i;

/** Texto do irmão anterior na árvore Lezer, pulando comentários (nulo se não houver). */
function prevTokenText(node: SyntaxNode, doc: Text): string | null {
  let prev = node.prevSibling;
  while (prev && (prev.name === "LineComment" || prev.name === "BlockComment")) prev = prev.prevSibling;
  return prev ? doc.sliceString(prev.from, prev.to) : null;
}

/**
 * SQL: o lang-sql etiqueta todo identificador como `name`, sem distinguir o
 * qualificador (`main.schema.`) do nome final. Marca os identificadores
 * seguidos de `.` + nome (qualificador), o segmento logo após o qualificador
 * (nome de tabela; `alias.coluna` também cai aqui, a gramática não distingue)
 * e o identificador não qualificado seguido de `(` (chamada de função).
 * Exceção: se o token anterior (Lezer, sem espaços/comentários) for TABLE,
 * INTO, VIEW ou EXISTS, é nome de tabela em DDL/DML e fica neutro.
 * Identificador não qualificado cujo texto é tipo do Spark ausente da lista do lang-sql
 * (BIGINT, STRING…) recebe a cor de tipo (papel de classe). Os demais identificadores
 * sem qualificador ficam com a tag `name` (papel de variável).
 */
function qualifierDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  const doc = view.state.doc;
  for (const { from, to } of view.visibleRanges) {
    syntaxTree(view.state).iterate({
      from,
      to,
      enter: (node) => {
        if (node.name !== "Identifier" && node.name !== "QuotedIdentifier") return;
        const next = doc.sliceString(node.to, Math.min(node.to + 2, doc.length));
        if (QUALIFIER_TAIL.test(next)) {
          // Inclui o `.` seguinte: o qualificador (`bronze.`) inteiro tem a cor de módulo.
          builder.add(node.from, node.to + 1, qualifierMark);
          return;
        }
        const prev = doc.sliceString(Math.max(node.from - 2, 0), node.from);
        if (QUALIFIED_HEAD.test(prev)) {
          builder.add(node.from, node.to, tableMark);
          return;
        }
        if (node.name === "Identifier" && SPARK_EXTRA_TYPES.has(doc.sliceString(node.from, node.to).toLowerCase())) {
          builder.add(node.from, node.to, sqlTypeMark);
          return;
        }
        if (node.name === "Identifier") {
          const after = doc.sliceString(node.to, Math.min(node.to + 32, doc.length));
          if (!CALL_TAIL.test(after)) return;
          const prevToken = prevTokenText(node.node, doc);
          if (prevToken !== null && TABLE_INTRODUCER.test(prevToken)) return;
          builder.add(node.from, node.to, functionMark);
        }
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
const pyModuleMark = Decoration.mark({ class: "cm-py-module" });
/** Heurística de classe: maiúscula inicial e ao menos uma minúscula (`DataFrame`; não `F` nem `MAX_ROWS`). */
const PY_CLASS_NAME = /^_*[A-Z]\w*[a-z]\w*$/;
/** Pais em que o `VariableName` já tem papel próprio: chamada, definição e decorator. */
const PY_OWN_ROLE_PARENT = new Set(["CallExpression", "ClassDefinition", "FunctionDefinition", "Decorator"]);
const PY_IMPORT_DOT = new Set([".", "...", "Ellipsis"]);

type PyRole = "class" | "module";
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
 * chamada/definição/decorator, onde chamada e definição mantêm a própria cor) e
 * caminho de módulo em `import`/`from`. Os demais papéis (variável, atributo, chamada)
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
        if (PY_CLASS_NAME.test(doc.sliceString(node.from, node.to))) sink(node.from, node.to, "class");
      },
    });
  }
}

function pythonRoleDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  pythonRoles(view.state, view.visibleRanges, (from, to, role) =>
    builder.add(from, to, role === "class" ? pyClassMark : pyModuleMark),
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
