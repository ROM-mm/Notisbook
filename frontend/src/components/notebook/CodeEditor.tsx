/**
 * Wrapper React do CodeMirror 6 (controlado por `value`).
 *
 * - A view é criada uma vez por linguagem (a view é recriada quando `language` muda, ex.: tipo ou linguagem da célula).
 * - Mudanças externas de `value` (ex.: recarga) substituem o documento sem disparar `onChange`.
 * - Atalhos do notebook têm precedência máxima sobre o keymap padrão:
 *   Shift+Enter, Mod+Enter e Esc.
 */
import { closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { SQLDialect, sql } from "@codemirror/lang-sql";
import { bracketMatching, indentOnInput, indentUnit } from "@codemirror/language";
import { EditorState, type Extension, Prec } from "@codemirror/state";
import { EditorView, drawSelection, keymap, lineNumbers, placeholder as placeholderExt } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { notebookEditorTheme, sqlQualifierHighlight } from "./editorTheme";

// Spark SQL usa crase como aspas de identificador; StandardSQL só reconhece `"`.
// Sem `keywords`/`types` o define() herda os mesmos defaults do StandardSQL.
const sparkSqlDialect = SQLDialect.define({ identifierQuotes: '`"' });

export type EditorLanguage = "python" | "sql" | "markdown" | "plain";

export interface CodeEditorHandlers {
  onChange: (value: string) => void;
  onFocus?: () => void;
  onBlur?: () => void;
  /** Shift+Enter: executar/renderizar e avançar. */
  onShiftEnter?: () => void;
  /** Mod+Enter: executar/renderizar sem avançar. */
  onModEnter?: () => void;
  /** Esc: sair para o modo comando (o editor já perdeu o foco). */
  onEscape?: () => void;
}

export interface CodeEditorProps extends CodeEditorHandlers {
  value: string;
  language: EditorLanguage;
  /** Quando passa a `true`, o editor recebe o foco. */
  focused: boolean;
  placeholder?: string;
  ariaLabel?: string;
}

function languageExtension(language: EditorLanguage): Extension {
  switch (language) {
    case "python":
      return [python(), indentUnit.of("    ")];
    case "sql":
      return [sql({ dialect: sparkSqlDialect }), indentUnit.of("  "), sqlQualifierHighlight];
    case "markdown":
      return [markdown(), EditorView.lineWrapping];
    case "plain":
      return EditorView.lineWrapping;
  }
}

export function CodeEditor({ value, language, focused, placeholder, ariaLabel, ...handlers }: CodeEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const handlersRef = useRef<CodeEditorHandlers>(handlers);
  handlersRef.current = handlers;
  /** Evita propagar como edição do usuário a sincronização vinda de `value`. */
  const applyingExternal = useRef(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const notebookKeys = Prec.highest(
      keymap.of([
        {
          key: "Shift-Enter",
          run: () => {
            handlersRef.current.onShiftEnter?.();
            return true;
          },
        },
        {
          key: "Mod-Enter",
          run: () => {
            handlersRef.current.onModEnter?.();
            return true;
          },
        },
        {
          key: "Escape",
          run: (view) => {
            view.contentDOM.blur();
            handlersRef.current.onEscape?.();
            return true;
          },
        },
      ]),
    );
    const view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          notebookKeys,
          lineNumbers(),
          drawSelection({ drawRangeCursor: false }),
          history(),
          indentOnInput(),
          bracketMatching(),
          closeBrackets(),
          keymap.of([...closeBracketsKeymap, ...defaultKeymap, ...historyKeymap, indentWithTab]),
          languageExtension(language),
          notebookEditorTheme,
          placeholder ? placeholderExt(placeholder) : [],
          ariaLabel ? EditorView.contentAttributes.of({ "aria-label": ariaLabel }) : [],
          EditorView.updateListener.of((u) => {
            if (u.docChanged && !applyingExternal.current) handlersRef.current.onChange(u.state.doc.toString());
            if (u.focusChanged) {
              if (u.view.hasFocus) handlersRef.current.onFocus?.();
              else handlersRef.current.onBlur?.();
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // `value`/`placeholder` só no estado inicial; `value` é sincronizado no efeito abaixo.
  }, [language]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    applyingExternal.current = true;
    try {
      view.dispatch({ changes: { from: 0, to: current.length, insert: value } });
    } finally {
      applyingExternal.current = false;
    }
  }, [value]);

  useEffect(() => {
    const view = viewRef.current;
    if (focused && view && !view.hasFocus) view.focus();
  }, [focused]);

  return <div ref={hostRef} />;
}
