/** Diálogo "Keyboard shortcuts" (menu Help). */
import { useEffect, useRef } from "react";
import { useWorkspace } from "../../state/workspace";
import dlg from "../../styles/dialog.module.css";
import styles from "./AppShell.module.css";
import { CloseIcon } from "./icons";

const SHORTCUTS: [string, string][] = [
  ["⌘S / Ctrl+S", "Save the notebook"],
  ["Shift+Enter", "Run the cell and advance"],
  ["⌘Enter / Ctrl+Enter", "Run the cell and stay"],
  ["Esc", "Leave editing (command mode)"],
  ["Enter", "Edit the selected cell"],
  ["↑ / K, ↓ / J", "Select previous / next cell"],
  ["A / B", "Insert code cell above / below"],
  ["M / Y", "Convert to markdown / code"],
  ["D D", "Delete the cell"],
  ["⌘. / Ctrl+.", "Toggle focus mode"],
];

export function ShortcutsDialog() {
  const open = useWorkspace((s) => s.shortcutsOpen);
  const setOpen = useWorkspace((s) => s.setShortcutsOpen);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.shortcutsDialog}`}
      aria-labelledby="shortcuts-title"
      data-testid="shortcuts-dialog"
      onClose={() => setOpen(false)}
      onClick={(e) => e.target === e.currentTarget && setOpen(false)}
    >
      <header className={dlg.head}>
        <h2 id="shortcuts-title" className={dlg.title}>
          Keyboard shortcuts
        </h2>
        <button type="button" className={styles.iconBtn} aria-label="Close" onClick={() => setOpen(false)}>
          <CloseIcon size={14} />
        </button>
      </header>
      <dl className={styles.shortcuts}>
        {SHORTCUTS.map(([keys, what]) => (
          <div key={keys} className={styles.shortcutRow}>
            <dt>
              <kbd>{keys}</kbd>
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
    </dialog>
  );
}
