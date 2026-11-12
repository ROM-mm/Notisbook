/**
 * Dimensões redimensionáveis dos painéis. Só em memória, de propósito:
 * os tamanhos voltam ao padrão ao fechar o app.
 */
import { create } from "zustand";

export const DEFAULT_SIDE_PANEL_WIDTH = 288;
export const DEFAULT_RIGHT_PANEL_WIDTH = 320;

export const SIDE_PANEL_MIN = 200;
export const SIDE_PANEL_MAX = 600;

/**
 * Cartões de cada lateral, de cima para baixo (única fonte da composição e da
 * ordem). Esquerda: Catalog. Direita: Notebooks, Connections (chave `files`) e Variables.
 */
export const LEFT_CARDS = ["catalog"] as const;
export const RIGHT_CARDS = ["notebooks", "files", "variables"] as const;
export type PanelSide = "left" | "right";
export type PanelCard = (typeof LEFT_CARDS)[number] | (typeof RIGHT_CARDS)[number];

export const CARDS_BY_SIDE: Record<PanelSide, readonly PanelCard[]> = { left: LEFT_CARDS, right: RIGHT_CARDS };

export const DEFAULT_CARD_WEIGHTS: Record<PanelCard, number> = { catalog: 1, notebooks: 1, files: 1, variables: 1 };

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

interface LayoutState {
  sidePanelWidth: number;
  rightPanelWidth: number;
  /** Pesos de flex-grow dos cartões; só a proporção entre os abertos da mesma lateral importa. */
  cardWeights: Record<PanelCard, number>;
  cardCollapsed: Record<PanelCard, boolean>;
  setSidePanelWidth: (w: number) => void;
  setRightPanelWidth: (w: number) => void;
  setCardWeights: (weights: Partial<Record<PanelCard, number>>) => void;
  resetCardWeights: () => void;
  toggleCard: (card: PanelCard) => void;
  expandCard: (card: PanelCard) => void;
}

export const useLayout = create<LayoutState>()((set) => ({
  sidePanelWidth: DEFAULT_SIDE_PANEL_WIDTH,
  rightPanelWidth: DEFAULT_RIGHT_PANEL_WIDTH,
  cardWeights: { ...DEFAULT_CARD_WEIGHTS },
  cardCollapsed: { catalog: false, notebooks: false, files: false, variables: false },
  setSidePanelWidth: (w) => set({ sidePanelWidth: clamp(w, SIDE_PANEL_MIN, SIDE_PANEL_MAX) }),
  setRightPanelWidth: (w) => set({ rightPanelWidth: clamp(w, SIDE_PANEL_MIN, SIDE_PANEL_MAX) }),
  setCardWeights: (weights) => set((s) => ({ cardWeights: { ...s.cardWeights, ...weights } })),
  resetCardWeights: () => set({ cardWeights: { ...DEFAULT_CARD_WEIGHTS } }),
  toggleCard: (card) => set((s) => ({ cardCollapsed: { ...s.cardCollapsed, [card]: !s.cardCollapsed[card] } })),
  expandCard: (card) => set((s) => (s.cardCollapsed[card] ? { cardCollapsed: { ...s.cardCollapsed, [card]: false } } : s)),
}));
