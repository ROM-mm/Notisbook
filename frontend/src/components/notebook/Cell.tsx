/**
 * Uma célula do notebook no padrão do mock (`site/styles.css`, `.cell`): moldura de
 * 1px (mais forte na ativa), cabeçalho (`CellHeader`: nome da linguagem, status e
 * ações), o editor (markdown fora de edição é renderizado como texto) e, abaixo de
 * um tracejado, os slots.
 *
 * Slots (preenchidos pela NotebookView):
 * - `footer`: status do run (`data-testid="cell-duration"`).
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
  /** Posição 0-based (usada para habilitar "Move up"). */
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
  duckdb: "DuckDB query",
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

/** O foco atual (após o blur do editor) está dentro do contêiner desta célula. */
function focusInsideCell(id: string): boolean {
  const focused = document.activeElement;
  if (!(focused instanceof Element)) return false;
  return focused.closest("[data-cell-id]")?.getAttribute("data-cell-id") === id;
}

/**
 * Janela em que um blur do editor é atribuído a um mousedown dentro da própria célula.
 * O blur do DOM acontece na ação padrão do mousedown (independe do mouseup) e o CM6 só
 * avisa ~10 ms depois (`updateForFocusChange`); 100 ms cobre esse atraso com folga e
 * expira antes de qualquer blur genuíno posterior (clique fora, Tab para fora).
 */
const INTERNAL_MOUSEDOWN_WINDOW_MS = 100;

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

  // Mousedown recente dentro da própria célula (⋮, título, rótulo, padding). Safari e
  // Firefox no macOS não focam <button> no clique: o foco cai em `body` e
  // `focusInsideCell` não basta para reconhecer o clique interno.
  const internalMouseDown = useRef(false);
  const internalMouseDownTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(internalMouseDownTimer.current), []);

  const onMouseDown = (e: MouseEvent) => {
    internalMouseDown.current = true;
    window.clearTimeout(internalMouseDownTimer.current);
    internalMouseDownTimer.current = window.setTimeout(() => {
      internalMouseDown.current = false;
    }, INTERNAL_MOUSEDOWN_WINDOW_MS);
    const nb = store.getState();
    if (isInsideEditor(e.target)) nb.selectCell(id);
    else nb.selectCell(id, "command");
  };

  const startEditing = () => {
    const nb = store.getState();
    nb.setMarkdownEditing(id, true);
    nb.selectCell(id, "edit");
  };

  const className = active ? `${styles.cell} ${styles.cellActive}` : styles.cell;

  return (
    <div
      ref={ref}
      className={className}
      data-cell-id={id}
      data-cell-type={cell.cell_type}
      // Paleta de sintaxe por linguagem (Notebook.module.css); markdown/raw ficam no padrão.
      data-cell-language={cell.cell_type === "code" ? cellLanguage(cell) : undefined}
      data-testid="cell"
      onMouseDown={onMouseDown}
    >
      <CellHeader
        cell={cell}
        index={index}
        isLast={isLast}
        canRun={canRun}
        titleEditing={titleEditing}
        setTitleEditing={setTitleEditing}
      />

      <div className={styles.cellBody}>
        {showEditor ? (
          <div className={cell.cell_type === "code" ? styles.codeBox : styles.textBox}>
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
                // Markdown volta a renderizar quando o foco sai da célula. Não renderiza se o
                // blur veio de um clique dentro da própria célula (⋮, título, rótulo, padding,
                // mesmo sem foco no botão), se o foco foi para o ⋮/título nem no blur da
                // janela (Alt+Tab). Só lê o DOM/estado: a view pode já ter sido destruída.
                // Não executa nada.
                if (
                  isMarkdown &&
                  !internalMouseDown.current &&
                  document.hasFocus() &&
                  !focusInsideCell(id)
                )
                  nb.setMarkdownEditing(id, false);
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

        {/* Rodapé e saídas abaixo do tracejado; `:empty` some quando o rodapé não renderiza nada. */}
        {footer || hasOutputs ? (
          <div className={styles.cellOut}>
            {footer}
            {hasOutputs && <div className={styles.outputBox}>{outputs}</div>}
          </div>
        ) : null}
      </div>
    </div>
  );
});
