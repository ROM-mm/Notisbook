/**
 * Corpo do notebook da aba ativa: lista as células e trata os atalhos.
 * Menus e estado de salvamento ficam no header e os controles do kernel na
 * barra de abas (components/shell). Lê o notebook da aba via contexto
 * (`NotebookProvider`); só a aba ativa é montada, e a rolagem é salva em
 * `entry.view.scrollTop` para ser restaurada ao voltar à aba.
 *
 * Atalhos
 * - Global: Cmd/Ctrl+S salva.
 * - Modo edição (editor com foco): Shift+Enter executa/renderiza e avança;
 *   Cmd/Ctrl+Enter executa/renderiza sem avançar; Esc → modo comando.
 * - Modo comando: Enter edita; ↑/K e ↓/J navegam; A/B inserem code acima/abaixo;
 *   M/Y convertem em markdown/código; D D exclui; Shift+Enter executa e avança.
 *
 * Pontos de extensão
 * - Execução: `onRunCell(cellId)` é chamado para células code em
 *   Shift+Enter / Cmd+Enter / botão ▶; `renderOutputs` e `renderFooter`
 *   preenchem os slots `outputs`/`footer` de cada célula.
 */
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { notebookTitle } from "../../lib/paths";
import type { EditorCell, EditorCodeCell } from "../../state/notebook";
import { useNotebook, useNotebookEntry } from "../../state/notebookContext";
import { useWorkspace } from "../../state/workspace";
import { Placeholder } from "../shell/StatusScreen";
import { AddCellBar, insertAndEdit } from "./AddCellBar";
import { Cell } from "./Cell";
import styles from "./Notebook.module.css";

const DOUBLE_KEY_MS = 600;

export interface NotebookViewProps {
  /** Executa uma célula code (enviar `execute_request` pelo SessionChannel). */
  onRunCell?: (cellId: string) => void;
  /** Saídas renderizadas de uma célula code. */
  renderOutputs?: (cell: EditorCodeCell) => ReactNode;
  /** Rodapé de execução por célula. */
  renderFooter?: (cell: EditorCell) => ReactNode;
  /** Aviso exibido acima das células (ex.: sessão de kernel encerrada). */
  banner?: ReactNode;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return target.closest("input, textarea, select, button, dialog, [contenteditable='true']") !== null;
}

function blurActiveElement(): void {
  const el = document.activeElement;
  if (el instanceof HTMLElement) el.blur();
}

/** Aviso quando não há renderizador de saídas: nada vindo do disco é perdido. */
function PreservedOutputs({ cell }: { cell: EditorCodeCell }) {
  const n = cell.outputs.length;
  if (n === 0) return null;
  return (
    <p className={styles.preserved}>{n === 1 ? "1 output saved in the file" : `${n} outputs saved in the file`}</p>
  );
}

export function NotebookView({ onRunCell, renderOutputs, renderFooter, banner }: NotebookViewProps) {
  const entry = useNotebookEntry();
  const store = entry.notebook;
  const status = useNotebook((s) => s.status);
  const loadError = useNotebook((s) => s.loadError);
  const cells = useNotebook((s) => s.cells);
  const activeId = useNotebook((s) => s.activeId);
  const mode = useNotebook((s) => s.mode);
  const editingMarkdown = useNotebook((s) => s.editingMarkdown);
  const saveError = useNotebook((s) => s.saveError);
  const scrollRef = useRef<HTMLDivElement>(null);

  const runRef = useRef(onRunCell);
  runRef.current = onRunCell;

  // Rolagem preservada por aba.
  const ready = status === "ready";
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && ready) el.scrollTop = entry.view.scrollTop;
  }, [entry, ready]);

  // Executar / renderizar.
  const runCell = useCallback(
    (id: string, advance: boolean) => {
      const nb = store.getState();
      const index = nb.cells.findIndex((c) => c.id === id);
      const cell = nb.cells[index];
      if (!cell) return;
      if (cell.cell_type === "markdown") nb.setMarkdownEditing(id, false);
      else if (cell.cell_type === "code") runRef.current?.(id);
      blurActiveElement();
      if (!advance) {
        nb.selectCell(id, "command");
        return;
      }
      const next = nb.cells[index + 1];
      if (next) nb.selectCell(next.id, "command");
      else insertAndEdit(store, "below", id, "code");
    },
    [store],
  );

  // Teclado: Cmd+S global e modo comando (só a aba ativa está montada).
  useEffect(() => {
    let lastD = 0;
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void store.getState().save();
        return;
      }
      if (e.defaultPrevented || e.isComposing || isEditableTarget(e.target)) return;
      const nb = store.getState();
      if (nb.status !== "ready" || nb.mode !== "command" || !nb.activeId) return;
      const id = nb.activeId;
      if (e.key === "Enter" && e.shiftKey && !mod && !e.altKey) {
        e.preventDefault();
        runCell(id, true);
        return;
      }
      if (mod || e.altKey || e.shiftKey) return;
      const cell = nb.cells.find((c) => c.id === id);
      switch (e.key) {
        case "Enter":
          e.preventDefault();
          if (cell?.cell_type === "markdown") nb.setMarkdownEditing(id, true);
          nb.selectCell(id, "edit");
          break;
        case "ArrowUp":
        case "k":
          e.preventDefault();
          nb.selectAdjacent(-1);
          break;
        case "ArrowDown":
        case "j":
          e.preventDefault();
          nb.selectAdjacent(1);
          break;
        case "a":
          e.preventDefault();
          nb.selectCell(nb.insertCell("above", id, "code"), "command");
          break;
        case "b":
          e.preventDefault();
          nb.selectCell(nb.insertCell("below", id, "code"), "command");
          break;
        case "m":
          e.preventDefault();
          nb.changeCellType(id, "markdown");
          break;
        case "y":
          e.preventDefault();
          nb.changeCellType(id, "code");
          break;
        case "d": {
          e.preventDefault();
          const now = Date.now();
          if (now - lastD < DOUBLE_KEY_MS) {
            nb.deleteCell(id);
            lastD = 0;
          } else lastD = now;
          break;
        }
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [runCell, store]);

  let body: ReactNode;
  if (status === "error") {
    body = (
      <Placeholder title={notebookTitle(entry.path)}>
        <p>Could not open the notebook: {loadError}</p>
        <p className={styles.errorActions}>
          <button type="button" className="btn" onClick={() => useWorkspace.getState().reload(entry.path)}>
            Try again
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => useWorkspace.getState().closeTab(entry.path)}>
            Close tab
          </button>
        </p>
      </Placeholder>
    );
  } else if (!ready) {
    body = <p className={styles.loading}>Loading notebook…</p>;
  } else {
    body = (
      <div className={styles.cells}>
        {banner}
        {saveError ? (
          <div className={styles.banner} role="alert">
            {saveError}
          </div>
        ) : null}
        {cells.length === 0 ? (
          <div className={styles.empty}>
            <p>This notebook is empty.</p>
            <AddCellBar where="below" refId={null} persistent />
          </div>
        ) : (
          <>
            <AddCellBar where="above" refId={cells[0]?.id ?? null} />
            {cells.map((cell, i) => {
              const active = cell.id === activeId;
              return (
                <div key={cell.id}>
                  <Cell
                    cell={cell}
                    index={i}
                    isLast={i === cells.length - 1}
                    active={active}
                    editMode={active && mode === "edit"}
                    markdownEditing={Boolean(editingMarkdown[cell.id])}
                    onRun={runCell}
                    canRun={onRunCell !== undefined}
                    outputs={
                      cell.cell_type === "code" ? (
                        renderOutputs ? (
                          renderOutputs(cell)
                        ) : (
                          <PreservedOutputs cell={cell} />
                        )
                      ) : null
                    }
                    footer={renderFooter ? renderFooter(cell) : null}
                  />
                  <AddCellBar where="below" refId={cell.id} persistent={i === cells.length - 1} />
                </div>
              );
            })}
          </>
        )}
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className={styles.notebook}
      data-testid="notebook-view"
      data-path={entry.path}
      onScroll={(e) => {
        if (ready) entry.view.scrollTop = e.currentTarget.scrollTop;
      }}
    >
      {body}
    </div>
  );
}
