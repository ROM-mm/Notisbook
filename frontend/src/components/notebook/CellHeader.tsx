/**
 * Cabeçalho da célula (padrão do mock em `site/styles.css`, `.cell-head`): à esquerda
 * só o nome da linguagem (abre o seletor) ou `markdown`; título opcional
 * (`metadata.title`) ao centro; à direita o status da última execução (✓/✗) e as ações
 * ■ (só enquanto a célula roda) e ⋮ (título, tipo, mover, inserir, excluir), visíveis
 * no hover ou na célula ativa. Executar é só pelo teclado (Shift+Enter / Cmd+Enter).
 * O ■ chama o interrupt do kernel, que é global à sessão.
 */
import { type ReactNode, useEffect, useRef, useState } from "react";
import { type CellLanguage, cellLanguage, cellTitle, type EditorCell } from "../../state/notebook";
import { useKernel, useKernelStore, useNotebookStore } from "../../state/notebookContext";
import { Menu, type MenuItem } from "../shell/Menu";
import { MoreVerticalIcon, StopFilledIcon } from "../shell/icons";
import { insertAndEdit } from "./AddCellBar";
import styles from "./Notebook.module.css";

export interface CellHeaderProps {
  cell: EditorCell;
  /** Posição 0-based. */
  index: number;
  isLast: boolean;
  canRun: boolean;
  titleEditing: boolean;
  setTitleEditing: (editing: boolean) => void;
}

const LANGUAGE_LABEL: Record<CellLanguage, string> = { python: "python", sql: "spark sql", duckdb: "duckdb sql" };
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

  // Status da última execução: só aparece enquanto a célula guarda marca de execução
  // (contagem ou saída `error`) — trocar a linguagem limpa essa marca e some com o status.
  // Havendo run desta sessão, ele decide ok/erro; sem run, vale o que veio salvo.
  const runStatus = useKernel((s) => s.runs[id]?.status);
  let outcome: "ok" | "error" | null = null;
  if (cell.cell_type === "code") {
    const hasError = cell.outputs.some((o) => o.output_type === "error");
    const executed = hasError || cell.execution_count !== null;
    if (executed && (runStatus === "ok" || runStatus === "error")) outcome = runStatus;
    else if (executed && runStatus === undefined) outcome = hasError ? "error" : "ok";
  }

  let label: ReactNode;
  if (!isCode) {
    label = <span className={styles.cellLabel}>markdown</span>;
  } else {
    let languageControl: ReactNode;
    if (!canRun) {
      languageControl = <span className={styles.cellLabel}>{LANGUAGE_LABEL[language]}</span>;
    } else if (languageLocked) {
      languageControl = (
        <button
          type="button"
          className={styles.languageLocked}
          disabled
          title="Language locked while the cell is queued or running"
          aria-label="Cell language"
          data-testid="cell-language"
        >
          {LANGUAGE_LABEL[language]}
        </button>
      );
    } else {
      languageControl = (
        <Menu
          trigger={LANGUAGE_LABEL[language]}
          ariaLabel="Cell language"
          title="Cell language"
          variant="icon"
          testId="cell-language"
          items={languageItems}
        />
      );
    }
    label = <span className={styles.languageMenu}>{languageControl}</span>;
  }

  return (
    <div className={styles.cellHeader} data-cell-type={isCode ? language : "markdown"}>
      <div className={styles.headerLeft}>{label}</div>
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
        {outcome === "ok" ? (
          <span className={styles.statusOk} role="img" aria-label="Last run succeeded" data-testid="cell-status">
            ✓
          </span>
        ) : outcome === "error" ? (
          <span className={styles.statusError} role="img" aria-label="Last run failed" data-testid="cell-status">
            ✗
          </span>
        ) : null}
        <span className={styles.headerActions}>
          {isCode && running ? (
            <button
              type="button"
              className={`${styles.runBtn} ${styles.stopBtn}`}
              onClick={() => kernelStore.getState().interrupt()}
              onMouseDown={(e) => e.preventDefault()}
              title="Interrupt kernel"
              aria-label="Interrupt kernel"
              data-testid="cell-stop"
            >
              <StopFilledIcon size={11} />
            </button>
          ) : null}
          <Menu
            trigger={<MoreVerticalIcon size={13} />}
            ariaLabel="Cell actions"
            title="Cell actions"
            variant="icon"
            align="right"
            testId="cell-menu"
            items={items}
          />
        </span>
      </div>
    </div>
  );
}
