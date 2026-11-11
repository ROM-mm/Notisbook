/**
 * Dimensões redimensionáveis dos painéis. Só em memória, de propósito:
 * os tamanhos voltam ao padrão ao fechar o app.
 */
import { create } from "zustand";

export const DEFAULT_SIDE_PANEL_WIDTH = 288;
export const DEFAULT_VARIABLES_WIDTH = 380;

export const SIDE_PANEL_MIN = 200;
export const SIDE_PANEL_MAX = 600;
export const VARIABLES_MIN = 260;
export const VARIABLES_MAX = 700;

/** Cartões do Explorer, de cima para baixo. */
export const EXPLORER_CARDS = ["notebooks", "files", "catalog"] as const;
export type ExplorerCard = (typeof EXPLORER_CARDS)[number];

export const DEFAULT_CARD_WEIGHTS: Record<ExplorerCard, number> = { notebooks: 1, files: 1, catalog: 1 };

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

interface LayoutState {
  sidePanelWidth: number;
  variablesWidth: number;
  /** Pesos de flex-grow dos cartões; só a proporção entre os abertos importa. */
  cardWeights: Record<ExplorerCard, number>;
  cardCollapsed: Record<ExplorerCard, boolean>;
  setSidePanelWidth: (w: number) => void;
  setVariablesWidth: (w: number) => void;
  setCardWeights: (weights: Partial<Record<ExplorerCard, number>>) => void;
  resetCardWeights: () => void;
  toggleCard: (card: ExplorerCard) => void;
  expandCard: (card: ExplorerCard) => void;
}

export const useLayout = create<LayoutState>()((set) => ({
  sidePanelWidth: DEFAULT_SIDE_PANEL_WIDTH,
  variablesWidth: DEFAULT_VARIABLES_WIDTH,
  cardWeights: { ...DEFAULT_CARD_WEIGHTS },
  cardCollapsed: { notebooks: false, files: false, catalog: false },
  setSidePanelWidth: (w) => set({ sidePanelWidth: clamp(w, SIDE_PANEL_MIN, SIDE_PANEL_MAX) }),
  setVariablesWidth: (w) => set({ variablesWidth: clamp(w, VARIABLES_MIN, VARIABLES_MAX) }),
  setCardWeights: (weights) => set((s) => ({ cardWeights: { ...s.cardWeights, ...weights } })),
  resetCardWeights: () => set({ cardWeights: { ...DEFAULT_CARD_WEIGHTS } }),
  toggleCard: (card) => set((s) => ({ cardCollapsed: { ...s.cardCollapsed, [card]: !s.cardCollapsed[card] } })),
  expandCard: (card) => set((s) => (s.cardCollapsed[card] ? { cardCollapsed: { ...s.cardCollapsed, [card]: false } } : s)),
}));
