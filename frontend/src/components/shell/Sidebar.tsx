/**
 * Barra lateral estreita de ícones: só 2 itens — Dados e Notebooks.
 * Cada ícone abre/recolhe o painel lateral correspondente (`SidePanel`).
 */
import type { ComponentType } from "react";
import { type SidePanel, useWorkspace } from "../../state/workspace";
import styles from "./AppShell.module.css";
import { DatabaseIcon, NotebookIcon } from "./icons";

const NAV: { panel: SidePanel; label: string; testId: string; Icon: ComponentType<{ size?: number }> }[] = [
  { panel: "data", label: "Data", testId: "nav-data", Icon: DatabaseIcon },
  { panel: "notebooks", label: "Notebooks", testId: "nav-notebooks", Icon: NotebookIcon },
];

export function Sidebar() {
  const panel = useWorkspace((s) => s.panel);
  const togglePanel = useWorkspace((s) => s.togglePanel);

  return (
    <aside className={styles.rail}>
      <nav className={styles.railNav} aria-label="Main navigation" data-testid="sidebar-nav">
        {NAV.map(({ panel: p, label, testId, Icon }) => (
          <button
            key={p}
            type="button"
            className={styles.railItem}
            data-testid={testId}
            aria-pressed={panel === p}
            aria-label={label}
            title={label}
            onClick={() => togglePanel(p)}
          >
            <Icon size={18} />
          </button>
        ))}
      </nav>
    </aside>
  );
}
