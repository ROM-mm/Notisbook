/**
 * Tema: "system" segue `prefers-color-scheme`; "light"/"dark" forçam via
 * `data-theme` no <html>. A preferência explícita é guardada em localStorage
 * (conveniência por navegador; falha silenciosa se indisponível).
 */
import { create } from "zustand";

export type ThemePref = "system" | "light" | "dark";
const KEY = "notisbook.theme";

function readPref(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* storage indisponível */
  }
  return "system";
}

function applyPref(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
  applyFavicon(effectiveTheme(pref));
}

const media = window.matchMedia("(prefers-color-scheme: dark)");

export function effectiveTheme(pref: ThemePref): "light" | "dark" {
  if (pref === "system") return media.matches ? "dark" : "light";
  return pref;
}

/** Favicon SVG não lê variáveis CSS nem o tema forçado: troca o arquivo pelo tema efetivo. */
function applyFavicon(theme: "light" | "dark"): void {
  const link = document.getElementById("app-favicon");
  if (link) link.setAttribute("href", `/favicon-${theme}.svg`);
}

interface ThemeState {
  pref: ThemePref;
  systemDark: boolean;
  setPref: (pref: ThemePref) => void;
  /** Alterna claro/escuro a partir do tema efetivo atual. */
  toggle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  pref: readPref(),
  systemDark: media.matches,
  setPref: (pref) => {
    applyPref(pref);
    try {
      window.localStorage.setItem(KEY, pref);
    } catch {
      /* ignora */
    }
    set({ pref });
  },
  toggle: () => {
    const current = effectiveTheme(get().pref);
    get().setPref(current === "dark" ? "light" : "dark");
  },
}));

media.addEventListener("change", (e) => {
  useTheme.setState({ systemDark: e.matches });
  if (useTheme.getState().pref === "system") applyFavicon(e.matches ? "dark" : "light");
});

/** Aplica a preferência salva antes do primeiro render (evita flash). */
export function initTheme(): void {
  applyPref(useTheme.getState().pref);
}
