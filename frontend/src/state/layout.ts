/**
 * Dimensões redimensionáveis dos painéis. Só em memória, de propósito:
 * os tamanhos voltam ao padrão ao fechar o app.
 */
import { create } from "zustand";

export const DEFAULT_SIDE_PANEL_WIDTH = 288;
export const DEFAULT_VARIABLES_WIDTH = 380;
export const DEFAULT_CATALOG_RATIO = 0.5;

export const SIDE_PANEL_MIN = 200;
export const SIDE_PANEL_MAX = 600;
export const VARIABLES_MIN = 260;
export const VARIABLES_MAX = 700;
export const RATIO_MIN = 0.05;
export const RATIO_MAX = 0.95;

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

interface LayoutState {
  sidePanelWidth: number;
  variablesWidth: number;
  catalogRatio: number;
  setSidePanelWidth: (w: number) => void;
  setVariablesWidth: (w: number) => void;
  setCatalogRatio: (r: number) => void;
}

export const useLayout = create<LayoutState>()((set) => ({
  sidePanelWidth: DEFAULT_SIDE_PANEL_WIDTH,
  variablesWidth: DEFAULT_VARIABLES_WIDTH,
  catalogRatio: DEFAULT_CATALOG_RATIO,
  setSidePanelWidth: (w) => set({ sidePanelWidth: clamp(w, SIDE_PANEL_MIN, SIDE_PANEL_MAX) }),
  setVariablesWidth: (w) => set({ variablesWidth: clamp(w, VARIABLES_MIN, VARIABLES_MAX) }),
  setCatalogRatio: (r) => set({ catalogRatio: clamp(r, RATIO_MIN, RATIO_MAX) }),
}));
