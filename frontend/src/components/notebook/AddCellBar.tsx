/** Barra discreta entre células para inserir code/markdown (aparece no hover). */
import { type EditableCellType, type InsertWhere, type NotebookStore } from "../../state/notebook";
import { useNotebookStore } from "../../state/notebookContext";
import { PlusIcon } from "../shell/icons";
import styles from "./Notebook.module.css";

export interface AddCellBarProps {
  where: InsertWhere;
  /** Célula de referência; null = início/fim do notebook. */
  refId: string | null;
  /** Sempre visível (ex.: notebook vazio ou fim da lista). */
  persistent?: boolean;
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

export function AddCellBar({ where, refId, persistent = false }: AddCellBarProps) {
  const store = useNotebookStore();
  return (
    <div className={persistent ? `${styles.addBar} ${styles.addBarPersistent}` : styles.addBar}>
      <span className={styles.addLine} aria-hidden="true" />
      <button type="button" className={styles.addBtn} onClick={() => insertAndEdit(store, where, refId, "code")}>
        <PlusIcon size={12} /> Code
      </button>
      <button type="button" className={styles.addBtn} onClick={() => insertAndEdit(store, where, refId, "markdown")}>
        <PlusIcon size={12} /> Markdown
      </button>
      <span className={styles.addLine} aria-hidden="true" />
    </div>
  );
}
