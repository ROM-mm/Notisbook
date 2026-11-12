/**
 * Uma célula do notebook (estilo terminal): cabeçalho (`CellHeader`:
 * ▶/■, linguagem e ações), faixa de fundo sem borda com o editor (em células
 * code, o "›" fica à esquerda dele; markdown é renderizado como texto) e slots.
 *
 * Slots (preenchidos pela NotebookView):
 * - `footer`: status do run, logo abaixo da faixa (`data-testid="cell-duration"`).
 * - `outputs`: saídas abaixo do status (renderizadores em components/outputs).
 */
import { memo, type MouseEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { type CellLanguage, cellLanguage, type EditorCell } from "../../state/notebook";
import { useNotebookStore } from "../../state/notebookContext";
import { Markdown } from "../outputs/Markdown";
import { CellHeader } from "./CellHeader";
import { CodeEditor, type EditorLanguage } from "./CodeEditor";
import styles from "./Notebook.module.css";

export interface CellProps {
  cell: EditorCell;
  /** Posição 0-based (o cabeçalho mostra `index + 1`). */
  index: number;
  isLast: boolean;
  active: boolean;
  /** Célula ativa em modo edição (o editor deve ter o foco). */
  editMode: boolean;
  /** Markdown aberto no editor (caso contrário, renderizado). */
  markdownEditing: boolean;
  /** Executa (code) / renderiza (markdown); `advance` seleciona a próxima célula. */
  onRun: (id: string, advance: boolean) => void;
  /** Mostra o botão de executar em células code. */
  canRun: boolean;
  outputs?: ReactNode;
  footer?: ReactNode;
}

const CODE_PLACEHOLDER: Record<CellLanguage, string> = {
  python: "Python code",
  sql: "Spark SQL query",
  duckdb: "DuckDB SQL query",
};

function languageOf(cell: EditorCell): EditorLanguage {
  if (cell.cell_type === "code") return cellLanguage(cell) === "python" ? "python" : "sql";
  if (cell.cell_type === "markdown") return "markdown";
  return "plain";
}

function placeholderOf(cell: EditorCell): string {
  if (cell.cell_type === "markdown") return "Write markdown…";
  if (cell.cell_type === "code") return CODE_PLACEHOLDER[cellLanguage(cell)];
  return "";
}

function isInsideEditor(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(".cm-editor") !== null;
}

export const Cell = memo(function Cell({
  cell,
  index,
  isLast,
  active,
  editMode,
  markdownEditing,
  onRun,
  canRun,
  outputs,
  footer,
}: CellProps) {
  const store = useNotebookStore();
  const ref = useRef<HTMLDivElement>(null);
  const [titleEditing, setTitleEditing] = useState(false);
  const id = cell.id;
  const isMarkdown = cell.cell_type === "markdown";
  const showEditor = !isMarkdown || markdownEditing;
  // Os renderizadores devolvem null sem saídas; o wrapper (e sua linha) só existe com saída.
  const hasOutputs = cell.cell_type === "code" && cell.outputs.length > 0 && Boolean(outputs);

  // Rola até a célula quando ela PASSA a ser ativa (não na montagem: a view
  // restaura a rolagem salva da aba).
  const mounted = useRef(false);
  useEffect(() => {
    if (mounted.current && active) ref.current?.scrollIntoView({ block: "nearest" });
    mounted.current = true;
  }, [active]);

  const onMouseDown = (e: MouseEvent) => {
    const nb = store.getState();
    if (isInsideEditor(e.target)) nb.selectCell(id);
    else nb.selectCell(id, "command");
  };

  const startEditing = () => {
    const nb = store.getState();
    nb.setMarkdownEditing(id, true);
    nb.selectCell(id, "edit");
  };

  const className = [styles.cell, active ? styles.cellActive : "", editMode ? styles.cellEditing : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={ref}
      className={className}
      data-cell-id={id}
      data-cell-type={cell.cell_type}
      data-testid="cell"
      onMouseDown={onMouseDown}
    >
      <CellHeader
        cell={cell}
        index={index}
        isLast={isLast}
        canRun={canRun}
        markdownEditing={markdownEditing}
        onRun={() => onRun(id, false)}
        titleEditing={titleEditing}
        setTitleEditing={setTitleEditing}
      />

      <div className={styles.cellBody}>
        {showEditor ? (
          <div className={cell.cell_type === "code" ? styles.codeBox : styles.textBox}>
            {cell.cell_type === "code" ? (
              <span className={styles.prompt} aria-hidden="true">
                ›
              </span>
            ) : null}
            <CodeEditor
              key={`${cell.cell_type}:${languageOf(cell)}`}
              value={cell.source}
              language={languageOf(cell)}
              focused={editMode}
              placeholder={placeholderOf(cell)}
              ariaLabel={isMarkdown ? "Markdown editor" : "Code editor"}
              onChange={(v) => store.getState().setSource(id, v)}
              onFocus={() => store.getState().selectCell(id, "edit")}
              onBlur={() => {
                const nb = store.getState();
                if (nb.activeId === id && nb.mode === "edit") nb.setMode("command");
              }}
              onShiftEnter={() => onRun(id, true)}
              onModEnter={() => onRun(id, false)}
              onEscape={() => {
                const nb = store.getState();
                if (isMarkdown) nb.setMarkdownEditing(id, false);
                nb.selectCell(id, "command");
              }}
            />
          </div>
        ) : (
          <div className={styles.rendered} onDoubleClick={startEditing} title="Double-click to edit">
            {cell.source.trim() ? (
              <Markdown source={cell.source} />
            ) : (
              <p className={styles.emptyMarkdown}>Empty markdown — double-click to edit.</p>
            )}
          </div>
        )}

        {footer}
        {hasOutputs && <div className={styles.outputBox}>{outputs}</div>}
      </div>
    </div>
  );
});
