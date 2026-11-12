import type { CSSProperties, ReactNode } from "react";

import styles from "./DataPanel.module.css";

/** Logo de marca em P&B (filtro em `.brandIcon`); `size` em px (padrão 14) via `--brand-size`. */
export function BrandIcon({ src, size = 14 }: { src: string; size?: number }): ReactNode {
  return (
    <img
      className={styles.brandIcon}
      style={{ "--brand-size": `${size}px` } as CSSProperties}
      src={src}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      draggable={false}
    />
  );
}
