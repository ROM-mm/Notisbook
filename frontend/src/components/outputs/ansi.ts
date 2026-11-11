/**
 * Texto de terminal (ANSI) → HTML escapado, via `ansi_up`.
 *
 * O resultado é HTML com `<span class="ansi-*-fg">` e texto escapado; quem o
 * injeta no DOM ainda passa por `DOMPurify.sanitize` no próprio componente
 * (regra do projeto). Nenhuma sequência `ESC[` sobrevive: o `ansi_up`
 * consome as CSI conhecidas e `stripEscapes` remove o que restar.
 */
import { AnsiUp } from "ansi_up";

const ESC = String.fromCharCode(0x1b);
/** CSI/OSC residuais e ESC soltos que o ansi_up não tenha consumido. */
const LEFTOVER_ESCAPES = new RegExp(`${ESC}(?:\\[[0-?]*[ -/]*[@-~]|\\][^${ESC}\\u0007]*(?:\\u0007|${ESC}\\\\)?)?`, "g");

export function stripEscapes(text: string): string {
  return text.includes(ESC) ? text.replace(LEFTOVER_ESCAPES, "") : text;
}

/** ANSI → HTML escapado (classes `ansi-<cor>-fg/bg`; truecolor vira `style`). */
export function ansiToHtml(text: string): string {
  // Instância nova por chamada: o AnsiUp guarda estado/buffer entre chamadas.
  const au = new AnsiUp();
  au.use_classes = true;
  au.escape_html = true;
  return stripEscapes(au.ansi_to_html(text));
}

/**
 * Aplica `\r` (retorno de carro) como um terminal: em cada linha, o texto após
 * o último `\r` sobrescreve o início. `\r\n` é tratado como quebra de linha.
 */
export function applyCarriageReturns(text: string): string {
  if (!text.includes("\r")) return text;
  return text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => {
      if (!line.includes("\r")) return line;
      let out = "";
      for (const part of line.split("\r")) out = part + out.slice(part.length);
      return out;
    })
    .join("\n");
}
