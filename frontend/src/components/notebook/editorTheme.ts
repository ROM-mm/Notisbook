/**
 * Tema do CodeMirror 6 integrado aos tokens do app. Todas as cores são
 * `var(--...)`, então a troca claro/escuro (data-theme / prefers-color-scheme)
 * se aplica sem reconfigurar o editor. As cores de sintaxe (`--syntax-*`) são
 * definidas em `Notebook.module.css`, no contêiner do notebook.
 */
import { HighlightStyle, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate } from "@codemirror/view";
import { type Extension, RangeSetBuilder } from "@codemirror/state";
import { tags as t } from "@lezer/highlight";

const theme = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    color: "var(--color-text)",
    fontSize: "13.5px",
  },
  ".cm-content, .cm-gutters": {
    fontWeight: "500",
  },
  // O `*` vence o span de `special(string)` do QuotedIdentifier, aninhado ou não.
  ".cm-sql-qualifier, .cm-sql-qualifier *": { color: "var(--syntax-qualifier)" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--font-code)",
    lineHeight: "var(--line-height-code)",
    overflow: "auto",
  },
  ".cm-content": {
    fontFamily: "var(--font-code)",
    padding: "0",
    caretColor: "var(--color-text)",
  },
  ".cm-gutters": {
    fontFamily: "var(--font-code)",
    backgroundColor: "transparent",
    color: "var(--color-text-muted)",
    border: "none",
  },
  // Gutter e linha ativa sem fundo próprio: o fundo da faixa da célula já destaca a linha.
  ".cm-activeLine, .cm-activeLineGutter": { backgroundColor: "transparent" },
  ".cm-activeLineGutter": { color: "var(--color-text)" },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 var(--space-3) 0 var(--space-2)", fontSize: "12px" },
  ".cm-line": { padding: "0" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--color-text)" },
  ".cm-placeholder": { color: "var(--color-text-subtle)", fontStyle: "normal" },
  "&.cm-focused .cm-matchingBracket": {
    backgroundColor: "var(--color-accent-subtle)",
    outline: "1px solid var(--color-focus-ring)",
  },
  "&.cm-focused .cm-nonmatchingBracket": { backgroundColor: "var(--color-danger-subtle)" },
  ".cm-content ::selection, .cm-line::selection": { backgroundColor: "var(--color-editor-selection)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "var(--color-editor-selection)" },
});

const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword], color: "var(--syntax-keyword)", fontWeight: "700" },
  { tag: [t.definitionKeyword, t.self, t.null, t.bool], color: "var(--syntax-keyword)", fontWeight: "700" },
  { tag: [t.string, t.special(t.string), t.regexp], color: "var(--syntax-string)" },
  { tag: [t.number, t.integer, t.float], color: "var(--syntax-number)" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "var(--syntax-comment)" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "var(--syntax-function)" },
  { tag: [t.definition(t.variableName), t.definition(t.function(t.variableName))], color: "var(--syntax-definition)" },
  { tag: [t.className, t.typeName, t.namespace], color: "var(--syntax-type)" },
  { tag: [t.operator, t.punctuation, t.bracket], color: "var(--syntax-punctuation)" },
  { tag: [t.meta, t.annotation, t.processingInstruction], color: "var(--syntax-meta)" },
  { tag: t.propertyName, color: "var(--syntax-property)" },
  // markdown
  { tag: t.heading, color: "var(--syntax-heading)", fontWeight: "600" },
  { tag: t.strong, fontWeight: "600" },
  { tag: t.emphasis, fontStyle: "italic" },
  { tag: t.strikethrough, textDecoration: "line-through" },
  { tag: [t.link, t.url], color: "var(--syntax-link)" },
  { tag: t.monospace, color: "var(--syntax-string)" },
  { tag: t.quote, color: "var(--syntax-comment)" },
  { tag: t.contentSeparator, color: "var(--syntax-punctuation)" },
  { tag: t.invalid, color: "var(--color-danger)" },
]);

export const notebookEditorTheme: Extension = [theme, syntaxHighlighting(highlight)];

const qualifierMark = Decoration.mark({ class: "cm-sql-qualifier" });
const QUALIFIER_TAIL = /^\.[\w"`]/;

/**
 * SQL: o lang-sql etiqueta todo identificador como `name`, sem distinguir o
 * qualificador (`main.schema.`) do nome final. Marca os identificadores
 * seguidos de `.` + nome; o último segmento e as colunas ficam neutros.
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
          builder.add(node.from, node.to, qualifierMark);
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
