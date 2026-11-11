/** Painel lateral recolhível (Explorer): título + X. */
import type { ReactNode } from "react";
import { useWorkspace } from "../../state/workspace";
import styles from "./AppShell.module.css";
import { CloseIcon } from "./icons";

export function SidePanel({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  const setExplorerOpen = useWorkspace((s) => s.setExplorerOpen);
  return (
    <section className={styles.panel} aria-label={title} data-testid="side-panel">
      <header className={styles.panelHeader}>
        <h2 className={styles.panelTitle}>{title}</h2>
        <div className={styles.panelActions}>
          {actions}
          <button
            type="button"
            className={styles.iconBtn}
            aria-label="Close panel"
            title="Close panel"
            onClick={() => setExplorerOpen(false)}
          >
            <CloseIcon size={14} />
          </button>
        </div>
      </header>
      <div className={styles.panelBody}>{children}</div>
    </section>
  );
}
