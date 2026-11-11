/** Título recolhível dos cartões do Explorer: botão com chevron que alterna o corpo. */
import type { ReactNode } from "react";
import { ChevronRightIcon } from "../shell/icons";
import styles from "./DataPanel.module.css";

interface CardTitleProps {
  id: string;
  icon: ReactNode;
  label: string;
  collapsed: boolean;
  onToggle: () => void;
  title?: string;
}

export function CardTitle({ id, icon, label, collapsed, onToggle, title }: CardTitleProps) {
  return (
    <h3 id={id} className={styles.sectionTitle} title={title}>
      <button type="button" className={styles.titleToggle} aria-expanded={!collapsed} onClick={onToggle}>
        <span className={`${styles.titleChevron} ${collapsed ? "" : styles.titleChevronOpen}`} aria-hidden="true">
          <ChevronRightIcon size={12} />
        </span>
        {icon} {label}
      </button>
    </h3>
  );
}
