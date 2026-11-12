/**
 * Pilha de cartões de uma lateral (composição em `LEFT_CARDS`/`RIGHT_CARDS`),
 * cada cartão com seu próprio scroll e recolhível. Alças horizontais entre
 * cartões abertos e adjacentes ajustam só os dois vizinhos (mín. 120px); duplo
 * clique restaura os pesos iniciais. Cartão recolhido não participa do
 * redimensionamento.
 */
import { Fragment, useRef, type ReactNode } from "react";
import { CARDS_BY_SIDE, useLayout, type PanelCard, type PanelSide } from "../../state/layout";
import { CatalogSection } from "../data/CatalogSection";
import { FilesSection } from "../data/FilesSection";
import { FileBrowser } from "../files/FileBrowser";
import { VariablesPanel } from "../variables/VariablesPanel";
import styles from "./Explorer.module.css";
import { ResizeHandle } from "./ResizeHandle";

// Altura mínima (px) de cada cartão durante o arraste.
const MIN_CARD_HEIGHT = 120;

const GRIP_LABELS: Record<PanelCard, string> = {
  catalog: "",
  notebooks: "Resize notebooks and connections sections",
  files: "Resize connections and variables sections",
  variables: "",
};

export function Explorer({ side }: { side: PanelSide }) {
  const cards = CARDS_BY_SIDE[side];
  const weights = useLayout((s) => s.cardWeights);
  const collapsed = useLayout((s) => s.cardCollapsed);
  const setWeights = useLayout((s) => s.setCardWeights);
  const resetWeights = useLayout((s) => s.resetCardWeights);
  const toggle = useLayout((s) => s.toggleCard);
  const expand = useLayout((s) => s.expandCard);
  const panelRef = useRef<HTMLDivElement>(null);
  const base = useRef({ above: 0, below: 0, sum: 0 });

  // O flex-grow é normalizado para somar 1 entre os abertos: com pesos < 1 o flex não preencheria o painel.
  const openTotal = cards.reduce((acc, c) => (collapsed[c] ? acc : acc + weights[c]), 0);

  const slotHeight = (card: PanelCard) =>
    panelRef.current?.querySelector(`[data-card="${card}"]`)?.getBoundingClientRect().height ?? 0;

  const dragStart = (above: PanelCard, below: PanelCard) => {
    const { cardWeights } = useLayout.getState();
    base.current = { above: slotHeight(above), below: slotHeight(below), sum: cardWeights[above] + cardWeights[below] };
  };

  const drag = (above: PanelCard, below: PanelCard, delta: number) => {
    const { above: hA, below: hB, sum } = base.current;
    const total = hA + hB;
    if (total <= 0) return;
    const min = Math.min(MIN_CARD_HEIGHT, total / 2);
    const next = Math.min(Math.max(hA + delta, min), total - min);
    const weightAbove = (sum * next) / total;
    setWeights({ [above]: weightAbove, [below]: sum - weightAbove });
  };

  const sections: Record<PanelCard, ReactNode> = {
    variables: <VariablesPanel collapsed={collapsed.variables} onToggle={() => toggle("variables")} />,
    notebooks: <FileBrowser collapsed={collapsed.notebooks} onToggle={() => toggle("notebooks")} onExpand={() => expand("notebooks")} />,
    files: <FilesSection collapsed={collapsed.files} onToggle={() => toggle("files")} onExpand={() => expand("files")} />,
    catalog: <CatalogSection testId="data-catalog" collapsed={collapsed.catalog} onToggle={() => toggle("catalog")} />,
  };

  return (
    <div className={styles.panel} ref={panelRef}>
      {cards.map((card, i) => {
        const below = cards[i + 1];
        const resizable = below !== undefined && !collapsed[card] && !collapsed[below];
        return (
          <Fragment key={card}>
            <div
              className={`${styles.slot} ${collapsed[card] ? styles.slotCollapsed : ""}`}
              data-card={card}
              style={collapsed[card] ? undefined : { flexGrow: weights[card] / openTotal }}
            >
              {sections[card]}
            </div>
            {below !== undefined ? (
              <div className={styles.gap}>
                {resizable ? (
                  <ResizeHandle
                    orientation="horizontal"
                    label={GRIP_LABELS[card]}
                    variant="gap"
                    onDragStart={() => dragStart(card, below)}
                    onDrag={(d) => drag(card, below, d)}
                    onReset={resetWeights}
                  />
                ) : null}
              </div>
            ) : null}
          </Fragment>
        );
      })}
    </div>
  );
}
