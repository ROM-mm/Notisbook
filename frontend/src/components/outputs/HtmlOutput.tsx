/**
 * Saída `text/html`: sanitizada pelo DOMPurify e montada num Shadow DOM,
 * que isola o CSS da saída (ex.: `<style>` do DataFrame do pandas) do resto da
 * página e vice-versa. Sem `<script>`, handlers `on*`, `<iframe>` nem `<form>`
 * (ver `HTML_OUTPUT_CONFIG`). O sanitizer devolve um DocumentFragment, que é
 * anexado sem reparse de string (evita mXSS).
 */
import DOMPurify from "dompurify";
import { memo, useLayoutEffect, useRef } from "react";
import styles from "./Outputs.module.css";
import { HTML_OUTPUT_CONFIG } from "./purify";

/** Estilo base dentro do shadow root (variáveis CSS do tema atravessam a fronteira). */
const SHADOW_CSS = `
:host { display: block; color: var(--color-text); font-family: var(--font-sans); font-size: 13px; line-height: 1.5; }
* { box-sizing: border-box; }
img, svg { max-width: 100%; height: auto; }
pre, code { font-family: var(--font-mono); font-size: 12.5px; }
table { border-collapse: collapse; border-spacing: 0; font-variant-numeric: tabular-nums; }
th, td { padding: 4px 10px; border: 0; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: top; white-space: nowrap; color: var(--color-text); }
td { font-family: var(--font-mono); font-size: 12.5px; }
thead th { background: var(--color-bg-panel); color: var(--color-text-muted); font-family: var(--font-mono); font-weight: 600; }
tbody tr:hover { background: var(--color-bg-hover); }
a { color: var(--color-accent-text); }
/* Alinhamento: tudo à esquerda, inclusive cabeçalho e colunas numéricas. O <style> do pandas (".dataframe thead th", 0,1,2) vem depois deste bloco e empata com ":host table th" (0,1,2); por isso o cabeçalho usa ":host table thead th" e ":host .dataframe thead th" (0,1,3), e th.num/td.num (0,2,2) vencem o ".nb-grid th.num" do kernel (0,2,1), sem !important. */
:host table th, :host table td, :host table thead th, :host .dataframe thead th, :host table th.num, :host table td.num { text-align: left; }
/* Grade de DataFrame: rolagem nos dois eixos; a moldura vai no contêiner. A tabela usa border-collapse: separate para o cabeçalho sticky ter caixa e borda próprias (no modo collapse a borda é da tabela e o cabeçalho fixo se desloca sobre a 1ª linha); o box-shadow mantém a linha sob o cabeçalho. O seletor do cabeçalho (0,1,3) vence o <style> do kernel (0,1,2), que vem depois. */
.nb-grid { max-height: 640px; overflow: auto; border: 1px solid var(--color-border); border-radius: 0; }
.nb-grid table { border: 0; border-collapse: separate; border-spacing: 0; }
.nb-grid > table > thead th { position: sticky; top: 0; z-index: 1; background: var(--color-bg-panel); box-shadow: inset 0 -1px 0 var(--color-border); border-bottom: 0; }
/* Rodapé fixo na base/esquerda da área rolável; fundo opaco e opacity:1 (o kernel põe opacity .7, que deixaria as linhas transparecerem); seletor composto vence o <style> do kernel, que vem depois. */
.nb-grid .nb-grid-footer { position: sticky; bottom: 0; left: 0; z-index: 2; opacity: 1; color: var(--color-text-muted); background: var(--color-bg); }
`;

export interface HtmlOutputProps {
  html: string;
}

export const HtmlOutput = memo(function HtmlOutput({ html }: HtmlOutputProps) {
  const hostRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // StrictMode monta duas vezes: reaproveita o shadow root existente.
    const root = host.shadowRoot ?? host.attachShadow({ mode: "open" });
    const clean = DOMPurify.sanitize(html, { ...HTML_OUTPUT_CONFIG, RETURN_DOM_FRAGMENT: true });
    const base = document.createElement("style");
    base.textContent = SHADOW_CSS;
    root.replaceChildren(base, clean);
  }, [html]);

  return <div ref={hostRef} className={styles.html} data-output-mime="text/html" />;
});
