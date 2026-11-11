/**
 * Painel Dados: Catalog (em cima) e Files (embaixo), separados por uma alça
 * horizontal que ajusta `catalogRatio`. Novas seções entram como irmãs de
 * <FilesSection /> dentro de `.panel`.
 */
import { useRef } from "react";
import { DEFAULT_CATALOG_RATIO, useLayout } from "../../state/layout";
import { ResizeHandle } from "../shell/ResizeHandle";
import { CatalogSection } from "./CatalogSection";
import { FilesSection } from "./FilesSection";
import styles from "./DataPanel.module.css";

// Altura mínima (px) de cada seção durante o arraste.
const MIN_SECTION_HEIGHT = 120;

export function DataPanel() {
  const ratio = useLayout((s) => s.catalogRatio);
  const setRatio = useLayout((s) => s.setCatalogRatio);
  const panelRef = useRef<HTMLDivElement>(null);
  const base = useRef({ ratio, height: 0 });

  const onDrag = (delta: number) => {
    const { ratio: r0, height } = base.current;
    if (height <= 0) return;
    const minRatio = Math.min(MIN_SECTION_HEIGHT / height, 0.5);
    const next = r0 + delta / height;
    setRatio(Math.min(Math.max(next, minRatio), 1 - minRatio));
  };

  return (
    <div className={styles.panel} ref={panelRef}>
      <div className={styles.slot} style={{ flexGrow: ratio }}>
        <CatalogSection testId="data-catalog" />
      </div>
      <ResizeHandle
        orientation="horizontal"
        label="Resize catalog and files sections"
        variant="gap"
        onDragStart={() => {
          base.current = {
            ratio: useLayout.getState().catalogRatio,
            height: panelRef.current?.getBoundingClientRect().height ?? 0,
          };
        }}
        onDrag={onDrag}
        onReset={() => setRatio(DEFAULT_CATALOG_RATIO)}
      />
      <div className={`${styles.slot} ${styles.slotFiles}`} style={{ flexGrow: 1 - ratio }}>
        <FilesSection />
      </div>
    </div>
  );
}
