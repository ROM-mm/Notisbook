/** Moldura de uma lateral (esquerda ou direita): largura própria e corpo com os cartões. */
import type { ReactNode } from "react";
import type { PanelSide } from "../../state/layout";
import styles from "./AppShell.module.css";

interface SidePanelProps {
  side: PanelSide;
  label: string;
  width: number;
  children: ReactNode;
}

export function SidePanel({ side, label, width, children }: SidePanelProps) {
  return (
    <section className={styles.panel} style={{ width }} aria-label={label} data-testid={`side-panel-${side}`}>
      <div className={styles.panelBody}>{children}</div>
    </section>
  );
}
