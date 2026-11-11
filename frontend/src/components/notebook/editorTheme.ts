/**
 * Tema do CodeMirror 6 integrado aos tokens do app. Todas as cores são
 * `var(--...)`, então a troca claro/escuro (data-theme / prefers-color-scheme)
 * se aplica sem reconfigurar o editor. As cores de sintaxe (`--syntax-*`) são
 * definidas em `Notebook.module.css`, no contêiner do notebook.
 */
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import type { Extension } from "@codemirror/state";
import { tags as t } from "@lezer/highlight";

const theme = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    color: "var(--color-text)",
    fontSize: "13.5px",
  },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    lineHeight: "var(--line-height-code)",
    overflow: "auto",
  },
  ".cm-content": {
    fontFamily: "var(--font-mono)",
    padding: "0",
    caretColor: "var(--color-text)",
  },
  ".cm-gutters": { fontFamily: "var(--font-mono)" },
  ".cm-line": { padding: "0" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--color-text)" },
  ".cm-placeholder": { color: "var(--color-text-subtle)", fontStyle: "normal" },
  "&.cm-focused .cm-matchingBracket": {
    backgroundColor: "var(--color-accent-subtle)",
    outline: "1px solid var(--color-focus-ring)",
  },
  "&.cm-focused .cm-nonmatchingBracket": { backgroundColor: "var(--color-danger-subtle)" },
  ".cm-content ::selection, .cm-line::selection": { backgroundColor: "var(--color-accent-subtle)" },
});

const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword], color: "var(--syntax-keyword)" },
  { tag: [t.definitionKeyword, t.self, t.null, t.bool], color: "var(--syntax-keyword)" },
  { tag: [t.string, t.special(t.string), t.regexp], color: "var(--syntax-string)" },
  { tag: [t.number, t.integer, t.float], color: "var(--syntax-number)" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "var(--syntax-comment)", fontStyle: "italic" },
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
