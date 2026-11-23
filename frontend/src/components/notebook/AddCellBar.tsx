/** Barra fina entre células para inserir code/markdown. */
import { type EditableCellType, type InsertWhere, type NotebookStore } from "../../state/notebook";
import { useNotebookStore } from "../../state/notebookContext";
import styles from "./Notebook.module.css";

export interface AddCellBarProps {
  where: InsertWhere;
  /** Célula de referência; null = início/fim do notebook. */
  refId: string | null;
}

export function insertAndEdit(
  store: NotebookStore,
  where: InsertWhere,
  refId: string | null,
  type: EditableCellType,
): void {
  const nb = store.getState();
  const id = nb.insertCell(where, refId, type);
  nb.selectCell(id, "edit");
}

export function AddCellBar({ where, refId }: AddCellBarProps) {
  const store = useNotebookStore();
  return (
    <div className={styles.addBar}>
      <span className={styles.addLine} aria-hidden="true" />
      <button
        type="button"
        className={styles.addBtn}
        aria-label="Add code cell"
        onClick={() => insertAndEdit(store, where, refId, "code")}
      >
        <span className={styles.addMark} aria-hidden="true" /> Code
      </button>
      <button
        type="button"
        className={styles.addBtn}
        aria-label="Add markdown cell"
        onClick={() => insertAndEdit(store, where, refId, "markdown")}
      >
        <span className={styles.addMark} aria-hidden="true" /> Markdown
      </button>
      <span className={styles.addLine} aria-hidden="true" />
    </div>
  );
}
