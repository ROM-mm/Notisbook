/**
 * Dimensões redimensionáveis dos painéis. Só em memória, de propósito:
 * os tamanhos voltam ao padrão ao fechar o app.
 */
import { create } from "zustand";

export const DEFAULT_SIDE_PANEL_WIDTH = 288;
export const DEFAULT_RIGHT_PANEL_WIDTH = 256;

export const SIDE_PANEL_MIN = 200;
export const SIDE_PANEL_MAX = 600;

/**
 * Cartões de cada lateral, de cima para baixo (única fonte da composição e da
 * ordem). Esquerda (dados): Catalog e, abaixo, Notislake/Connections (chave
 * `files`). Direita: Notebooks.
 */
export const LEFT_CARDS = ["catalog", "files"] as const;
export const RIGHT_CARDS = ["notebooks"] as const;
export type PanelSide = "left" | "right";
export type PanelCard = (typeof LEFT_CARDS)[number] | (typeof RIGHT_CARDS)[number];

export const CARDS_BY_SIDE: Record<PanelSide, readonly PanelCard[]> = { left: LEFT_CARDS, right: RIGHT_CARDS };

export const DEFAULT_CARD_WEIGHTS: Record<PanelCard, number> = { catalog: 1, notebooks: 1, files: 1 };

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

interface LayoutState {
  sidePanelWidth: number;
  rightPanelWidth: number;
  /** Verdadeiro após arraste manual: o ajuste automático ao conteúdo deixa de agir. */
  rightPanelWidthManual: boolean;
  /** Pesos de flex-grow dos cartões; só a proporção entre os abertos da mesma lateral importa. */
  cardWeights: Record<PanelCard, number>;
  cardCollapsed: Record<PanelCard, boolean>;
  setSidePanelWidth: (w: number) => void;
  setRightPanelWidth: (w: number) => void;
  /** Volta ao padrão e devolve o controle ao ajuste automático. */
  resetRightPanelWidth: () => void;
  /** Ajuste automático: só alarga (até SIDE_PANEL_MAX) e só sem arraste manual. */
  growRightPanelWidth: (w: number) => void;
  setCardWeights: (weights: Partial<Record<PanelCard, number>>) => void;
  resetCardWeights: () => void;
  toggleCard: (card: PanelCard) => void;
  expandCard: (card: PanelCard) => void;
}

export const useLayout = create<LayoutState>()((set) => ({
  sidePanelWidth: DEFAULT_SIDE_PANEL_WIDTH,
  rightPanelWidth: DEFAULT_RIGHT_PANEL_WIDTH,
  rightPanelWidthManual: false,
  cardWeights: { ...DEFAULT_CARD_WEIGHTS },
  cardCollapsed: { catalog: false, notebooks: false, files: false },
  setSidePanelWidth: (w) => set({ sidePanelWidth: clamp(w, SIDE_PANEL_MIN, SIDE_PANEL_MAX) }),
  setRightPanelWidth: (w) =>
    set((s) => {
      const next = clamp(w, SIDE_PANEL_MIN, SIDE_PANEL_MAX);
      // Largura inalterada (ex.: clique na alça sem arrastar) não conta como ajuste manual.
      return next === s.rightPanelWidth ? s : { rightPanelWidth: next, rightPanelWidthManual: true };
    }),
  resetRightPanelWidth: () => set({ rightPanelWidth: DEFAULT_RIGHT_PANEL_WIDTH, rightPanelWidthManual: false }),
  growRightPanelWidth: (w) =>
    set((s) => {
      // Mesmo teto do arraste manual (AppShell): metade da janela.
      const next = clamp(w, SIDE_PANEL_MIN, Math.min(SIDE_PANEL_MAX, window.innerWidth / 2));
      return s.rightPanelWidthManual || next <= s.rightPanelWidth ? s : { rightPanelWidth: next };
    }),
  setCardWeights: (weights) => set((s) => ({ cardWeights: { ...s.cardWeights, ...weights } })),
  resetCardWeights: () => set({ cardWeights: { ...DEFAULT_CARD_WEIGHTS } }),
  toggleCard: (card) => set((s) => ({ cardCollapsed: { ...s.cardCollapsed, [card]: !s.cardCollapsed[card] } })),
  expandCard: (card) => set((s) => (s.cardCollapsed[card] ? { cardCollapsed: { ...s.cardCollapsed, [card]: false } } : s)),
}));
