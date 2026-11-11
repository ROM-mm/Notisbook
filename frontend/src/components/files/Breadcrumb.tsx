import { Fragment } from "react";
import { crumbs } from "../../lib/paths";
import { ChevronRightIcon } from "../shell/icons";
import styles from "./Breadcrumb.module.css";

export interface BreadcrumbProps {
  /** Caminho relativo atual ("" = raiz). */
  path: string;
  /** Navega para um diretório ancestral. */
  onNavigate: (dir: string) => void;
  /** Rótulo da raiz. */
  rootLabel?: string;
  /** Se true, o último segmento também é clicável (ex.: arquivo aberto → pasta). */
  lastIsFile?: boolean;
}

/** Breadcrumb de diretórios; reutilizável pela view do notebook. */
export function Breadcrumb({ path, onNavigate, rootLabel = "Files", lastIsFile = false }: BreadcrumbProps) {
  const parts = crumbs(path);
  const items = [{ name: rootLabel, path: "" }, ...parts];

  return (
    <nav aria-label="Path" className={styles.crumbs}>
      {items.map((c, i) => {
        const isLast = i === items.length - 1;
        return (
          <Fragment key={c.path || "/"}>
            {i > 0 ? <ChevronRightIcon size={12} className={styles.sep} /> : null}
            {isLast ? (
              <span className={styles.current} aria-current={lastIsFile ? undefined : "page"} title={c.name}>
                {c.name}
              </span>
            ) : (
              <button type="button" className={styles.link} onClick={() => onNavigate(c.path)} title={c.name}>
                {c.name}
              </button>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
