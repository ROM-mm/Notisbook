import type { ReactNode } from "react";

import styles from "./DataPanel.module.css";

/** Logo de marca em P&B (filtro em `.brandIcon`), no mesmo padrão dos ícones do catálogo. */
export function BrandIcon({ src }: { src: string }): ReactNode {
  return <img className={styles.brandIcon} src={src} alt="" aria-hidden="true" width={14} height={14} draggable={false} />;
}
