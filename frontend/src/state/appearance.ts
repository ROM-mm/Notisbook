/**
 * Aparência: fonte da interface, do código e do markdown. A escolha fica em
 * localStorage (`notisbook.appearance`, JSON `{interface, code, markdown}`) e é
 * aplicada nos slots `--pref-font-*` de <html>; sem escolha, valem os defaults
 * dos tokens. Falha de storage é silenciosa, como em `theme.ts`.
 */
import { create } from "zustand";

export type FontSlot = "interface" | "code" | "markdown";
export type Appearance = Record<FontSlot, string>;

const KEY = "notisbook.appearance";
const SLOTS: readonly FontSlot[] = ["interface", "code", "markdown"];
export const MAX_FONT_NAME = 64;

/** Fontes empacotadas no app (fonts.css e @fontsource). */
export const BUNDLED_FONTS: readonly string[] = ["VT323", "Monocode", "Roboto"];

/** Iguais aos defaults de `--pref-font-*` em tokens.css. */
export const DEFAULT_APPEARANCE: Readonly<Appearance> = {
  interface: "VT323",
  code: "VT323",
  markdown: "Roboto",
};

// Sem fallback, uma fonte ausente cairia no serif padrão do navegador.
const SANS_FALLBACK = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const FALLBACK: Readonly<Appearance> = {
  interface: SANS_FALLBACK,
  code: "ui-monospace, SFMono-Regular, Menlo, monospace",
  markdown: SANS_FALLBACK,
};

// Rejeita o que escaparia de uma string CSS entre aspas: aspas, `\`, `;`, `{`, `}` e controles (inclui quebras de linha).
const FONT_NAME_PATTERN = /^[^"'\\;{}\u0000-\u001f\u007f]+$/;

/** Nome de fonte seguro para virar valor CSS entre aspas (já sem espaços nas pontas). */
export function isValidFontName(name: string): boolean {
  return name === name.trim() && name.length > 0 && name.length <= MAX_FONT_NAME && FONT_NAME_PATTERN.test(name);
}

/** Forma canônica de um nome digitado (sem espaços nas pontas); usada pelo `apply` e pela tela. */
export function normalizeFontName(name: string): string {
  return name.trim();
}

function read(): Appearance {
  const result: Appearance = { ...DEFAULT_APPEARANCE };
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw === null) return result;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return result;
    for (const slot of SLOTS) {
      const value = (parsed as Record<string, unknown>)[slot];
      if (typeof value === "string" && isValidFontName(value)) result[slot] = value;
    }
  } catch {
    /* storage indisponível ou JSON inválido */
  }
  return result;
}

function write(appearance: Appearance): void {
  try {
    const isDefault = SLOTS.every((slot) => appearance[slot] === DEFAULT_APPEARANCE[slot]);
    if (isDefault) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(appearance));
  } catch {
    /* ignora */
  }
}

/** Valor CSS de `font-family` do slot: nome entre aspas seguido dos fallbacks genéricos. */
export function fontFamilyValue(slot: FontSlot, name: string): string {
  return `"${name}", ${FALLBACK[slot]}`;
}

/** Nome sempre entre aspas; slot no default volta ao valor dos tokens. */
function applyToDom(appearance: Appearance): void {
  const style = document.documentElement.style;
  for (const slot of SLOTS) {
    const prop = `--pref-font-${slot}`;
    if (appearance[slot] === DEFAULT_APPEARANCE[slot]) style.removeProperty(prop);
    else style.setProperty(prop, fontFamilyValue(slot, appearance[slot]));
  }
}

interface AppearanceState {
  /** Escolha em vigor (a aplicada ao app). */
  current: Appearance;
  /**
   * Normaliza (trim), valida, aplica e salva; devolve a escolha aplicada ou, se algum nome for
   * inválido, o slot que falhou (sem alterar nada).
   */
  apply: (next: Appearance) => { ok: true; applied: Appearance } | { ok: false; slot: FontSlot };
}

export const useAppearance = create<AppearanceState>((set) => ({
  current: read(),
  apply: (next) => {
    const normalized = { ...DEFAULT_APPEARANCE };
    for (const slot of SLOTS) {
      const name = normalizeFontName(next[slot]);
      if (!isValidFontName(name)) return { ok: false, slot };
      normalized[slot] = name;
    }
    applyToDom(normalized);
    write(normalized);
    set({ current: normalized });
    return { ok: true, applied: normalized };
  },
}));

let started = false;

/** Aplica a escolha salva antes do primeiro render (evita flash) e acompanha outras abas. */
export function initAppearance(): void {
  applyToDom(useAppearance.getState().current);
  if (started) return;
  started = true;
  // `key === null`: outra aba chamou `localStorage.clear()`.
  window.addEventListener("storage", (e) => {
    if (e.key !== KEY && e.key !== null) return;
    const current = read();
    applyToDom(current);
    useAppearance.setState({ current });
  });
}
