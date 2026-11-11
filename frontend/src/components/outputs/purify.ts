/**
 * Configurações do DOMPurify para saídas de célula. Cada componente que injeta
 * HTML chama o sanitize do DOMPurify com uma destas configs no próprio arquivo
 * (regra do projeto: a sanitização fica visível junto da injeção).
 */
import type { Config } from "dompurify";

/** Tags que nunca entram numa saída: execução, navegação ou captura de dados. */
const FORBIDDEN_TAGS = [
  "script",
  "iframe",
  "frame",
  "frameset",
  "object",
  "embed",
  "form",
  "input",
  "button",
  "textarea",
  "select",
  "option",
  "base",
  "link",
  "meta",
  "noscript",
];

/** HTML de saída (`text/html`): perfil HTML, `<style>` permitido (fica no Shadow DOM). */
export const HTML_OUTPUT_CONFIG = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: FORBIDDEN_TAGS,
  FORBID_ATTR: ["action", "formaction", "srcdoc", "ping"],
  ADD_TAGS: ["style"],
  // Sem FORCE_BODY um `<style>` inicial cai no <head> e é descartado.
  FORCE_BODY: true,
  ALLOW_DATA_ATTR: false,
} satisfies Config;

/** HTML gerado pelo ansi_up: só `<span>` com class/style e links http(s). */
export const ANSI_CONFIG = {
  ALLOWED_TAGS: ["span", "a"],
  ALLOWED_ATTR: ["class", "style", "href"],
} satisfies Config;
