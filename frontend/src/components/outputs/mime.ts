/** Escolha de MIME de um bundle nbformat (preferência HTML > imagem > markdown > texto). */
import { joinMultiline, type MimeBundle, type MultilineString } from "../../api/nbformat";

/**
 * Ordem de preferência. `application/javascript` e ipywidgets
 * (`application/vnd.jupyter.widget-view+json`) não estão aqui de propósito:
 * sem execução de JS em saídas, o bundle cai para `text/plain`.
 */
export const MIME_PREFERENCE = [
  "text/html",
  "image/png",
  "image/jpeg",
  "image/svg+xml",
  "text/markdown",
  "text/plain",
] as const;

export type SupportedMime = (typeof MIME_PREFERENCE)[number];

function isMultiline(value: unknown): value is MultilineString {
  return typeof value === "string" || (Array.isArray(value) && value.every((v) => typeof v === "string"));
}

/** Primeiro MIME suportado presente no bundle, com o valor já como string. */
export function pickMime(data: MimeBundle): { mime: SupportedMime; value: string } | null {
  for (const mime of MIME_PREFERENCE) {
    const raw = data[mime];
    if (isMultiline(raw)) return { mime, value: joinMultiline(raw) };
  }
  return null;
}

/** UTF-8 → base64 (para SVG como data URL). */
export function utf8ToBase64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}
