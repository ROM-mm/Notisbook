/**
 * Tema: "system" segue `prefers-color-scheme`; "light"/"dark" forçam via
 * `data-theme` no <html>. "light-colorized"/"dark-colorized" são temas próprios com
 * os mesmos tokens do claro/escuro (`data-theme` base) e ícones coloridos, ligados por
 * `data-icons="colorized"` no <html> (a paleta `--ico-*` vive só sob esse seletor).
 * A preferência explícita é guardada em localStorage (conveniência por navegador;
 * falha silenciosa se indisponível).
 */
import { create } from "zustand";

export type ThemePref = "system" | "light" | "dark" | "light-colorized" | "dark-colorized";
const KEY = "notisbook.theme";

const PREFS: readonly ThemePref[] = ["system", "light", "dark", "light-colorized", "dark-colorized"];

function isThemePref(v: string | null): v is ThemePref {
  return v !== null && (PREFS as readonly string[]).includes(v);
}

function readPref(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY);
    if (isThemePref(v)) return v;
  } catch {
    /* storage indisponível */
  }
  return "system";
}

function isColorized(pref: ThemePref): boolean {
  return pref === "light-colorized" || pref === "dark-colorized";
}

/** Tema base (tokens) de uma preferência explícita; "system" não tem base fixa. */
function baseTheme(pref: Exclude<ThemePref, "system">): "light" | "dark" {
  return pref === "dark" || pref === "dark-colorized" ? "dark" : "light";
}

function applyPref(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", baseTheme(pref));
  if (isColorized(pref)) root.setAttribute("data-icons", "colorized");
  else root.removeAttribute("data-icons");
  applyFavicon(effectiveTheme(pref));
}

const media = window.matchMedia("(prefers-color-scheme: dark)");

export function effectiveTheme(pref: ThemePref): "light" | "dark" {
  if (pref === "system") return media.matches ? "dark" : "light";
  return baseTheme(pref);
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
  /** Alterna claro/escuro a partir do tema efetivo atual (preserva a variante colorized). */
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
    const { pref } = get();
    const next = effectiveTheme(pref) === "dark" ? "light" : "dark";
    get().setPref(isColorized(pref) ? `${next}-colorized` : next);
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
