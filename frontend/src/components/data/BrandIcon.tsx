import type { ReactNode } from "react";

import type { TechIcon } from "../shell/techIcons";
import styles from "./DataPanel.module.css";

/** Ícone de tecnologia (catálogo ou formato de tabela) em `currentColor`; `size` em px (padrão 14). */
export function BrandIcon({ icon: Icon, size = 14 }: { icon: TechIcon; size?: number }): ReactNode {
  return <Icon className={styles.brandIcon} size={size} />;
}
