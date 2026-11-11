/**
 * Cabeçalho da célula (padrão Databricks): ▶, ■ e seletor Python/SQL à esquerda, título
 * opcional (`metadata.title`) centralizado e menu ⋮ à direita (título, tipo, mover,
 * inserir, excluir). O ■ chama o interrupt do kernel, que é global à sessão.
 */
import { useEffect, useRef, useState } from "react";
import { type CellLanguage, cellLanguage, cellTitle, type EditorCell } from "../../state/notebook";
import { useKernel, useKernelStore, useNotebookStore } from "../../state/notebookContext";
import { Menu, type MenuItem } from "../shell/Menu";
import { MoreVerticalIcon, PlayFilledIcon, StopFilledIcon } from "../shell/icons";
import { insertAndEdit } from "./AddCellBar";
import { CheckIcon } from "./icons";
import styles from "./Notebook.module.css";

export interface CellHeaderProps {
  cell: EditorCell;
  /** Posição 0-based. */
  index: number;
  isLast: boolean;
  canRun: boolean;
  markdownEditing: boolean;
  onRun: () => void;
  titleEditing: boolean;
  setTitleEditing: (editing: boolean) => void;
}

const LANGUAGE_LABEL: Record<CellLanguage, string> = { python: "Python", sql: "Spark SQL", duckdb: "DuckDB SQL" };
const LANGUAGES: CellLanguage[] = ["python", "sql", "duckdb"];

function TitleInput({ initial, onDone }: { initial: string; onDone: (value: string | null) => void }) {
  const [value, setValue] = useState(initial);
  const ref = useRef<HTMLInputElement>(null);
  const done = useRef(false);
  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);
  const finish = (v: string | null) => {
    if (done.current) return;
    done.current = true;
    onDone(v);
  };
  return (
    <input
      ref={ref}
      className={styles.titleInput}
      aria-label="Cell title"
      data-testid="cell-title-input"
      placeholder="Cell title"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          finish(value);
        } else if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          finish(null);
        }
      }}
      onBlur={() => finish(value)}
    />
  );
}

export function CellHeader({
  cell,
  index,
  isLast,
  canRun,
  markdownEditing,
  onRun,
  titleEditing,
  setTitleEditing,
}: CellHeaderProps) {
  const store = useNotebookStore();
  const kernelStore = useKernelStore();
  const id = cell.id;
  // Trocar a linguagem com a célula na fila ou em execução reescreve o código já despachado;
  const languageLocked = useKernel((s) => {
    const status = s.runs[id]?.status;
    return status === "running" || status === "queued";
  });
  // O ■ só vale para a célula em execução; na fila ela ainda não está rodando.
  const running = useKernel((s) => s.runs[id]?.status === "running");
  const title = cellTitle(cell);
  const isCode = cell.cell_type === "code";
  const target = isCode ? "markdown" : "code";
  const nb = () => store.getState();

  const items = (): MenuItem[] => [
    { label: title ? "Edit title" : "Add title", onSelect: () => setTitleEditing(true), testId: "cell-menu-title" },
    ...(title ? [{ label: "Remove title", onSelect: () => nb().setCellTitle(id, null) }] : []),
    "separator",
    {
      label: target === "code" ? "Convert to code" : "Convert to markdown",
      shortcut: target === "code" ? "Y" : "M",
      onSelect: () => nb().changeCellType(id, target),
    },
    "separator",
    { label: "Move up", disabled: index === 0, onSelect: () => nb().moveCell(id, -1) },
    { label: "Move down", disabled: isLast, onSelect: () => nb().moveCell(id, 1) },
    "separator",
    { label: "Insert code above", onSelect: () => insertAndEdit(store, "above", id, "code") },
    { label: "Insert code below", onSelect: () => insertAndEdit(store, "below", id, "code") },
    { label: "Insert markdown below", onSelect: () => insertAndEdit(store, "below", id, "markdown") },
    "separator",
    { label: "Delete cell", shortcut: "D D", danger: true, onSelect: () => nb().deleteCell(id) },
  ];

  const language = cellLanguage(cell);
  const languageItems = (): MenuItem[] =>
    LANGUAGES.map((l) => ({
      label: LANGUAGE_LABEL[l],
      checked: l === language,
      testId: `cell-language-${l}`,
      onSelect: () => nb().setCellLanguage(id, l),
    }));

  let left = null;
  if (isCode && canRun) {
    left = (
      <>
        <button
          type="button"
          className={styles.runBtn}
          onClick={onRun}
          onMouseDown={(e) => e.preventDefault()}
          title="Run cell (Shift+Enter)"
          aria-label="Run cell"
          data-testid="cell-run"
        >
          <PlayFilledIcon size={12} />
        </button>
        <button
          type="button"
          className={`${styles.runBtn} ${styles.stopBtn}`}
          onClick={() => kernelStore.getState().interrupt()}
          onMouseDown={(e) => e.preventDefault()}
          disabled={!running}
          title="Interrupt kernel"
          aria-label="Interrupt kernel"
          data-testid="cell-stop"
        >
          <StopFilledIcon size={12} />
        </button>
        <span className={styles.languageMenu}>
          {languageLocked ? (
            <button
              type="button"
              className={styles.languageLocked}
              disabled
              title="Language locked while the cell is queued or running"
              aria-label="Cell language"
              data-testid="cell-language"
            >
              {LANGUAGE_LABEL[language]}
              <span aria-hidden="true">▾</span>
            </button>
          ) : (
            <Menu
              trigger={
                <>
                  {LANGUAGE_LABEL[language]}
                  <span aria-hidden="true">▾</span>
                </>
              }
              ariaLabel="Cell language"
              title="Cell language"
              variant="icon"
              testId="cell-language"
              items={languageItems}
            />
          )}
        </span>
      </>
    );
  } else if (cell.cell_type === "markdown" && markdownEditing) {
    left = (
      <button
        type="button"
        className={styles.runBtn}
        onClick={onRun}
        onMouseDown={(e) => e.preventDefault()}
        title="Render (Shift+Enter)"
        aria-label="Render markdown"
      >
        <CheckIcon />
      </button>
    );
  }

  return (
    <div className={styles.cellHeader} data-cell-type={isCode ? language : "markdown"}>
      <div className={styles.headerLeft}>{left}</div>
      <div className={styles.headerCenter}>
        {titleEditing ? (
          <span className={styles.titleEditRow}>
            <TitleInput
              initial={title ?? ""}
              onDone={(v) => {
                if (v !== null) store.getState().setCellTitle(id, v);
                setTitleEditing(false);
              }}
            />
          </span>
        ) : (
          <button
            type="button"
            className={styles.titleButton}
            onClick={() => setTitleEditing(true)}
            title={title ? "Click to edit the title" : "Click to add a title"}
          >
            {title ? (
              <span className={styles.cellTitle} data-testid="cell-title">
                {title}
              </span>
            ) : (
              <span className={styles.titlePlaceholder}>Add title</span>
            )}
          </button>
        )}
      </div>
      <div className={styles.headerRight}>
        <Menu
          trigger={<MoreVerticalIcon size={14} />}
          ariaLabel="Cell actions"
          title="Cell actions"
          variant="icon"
          align="right"
          testId="cell-menu"
          items={items}
        />
      </div>
    </div>
  );
}
