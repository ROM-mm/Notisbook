/**
 * Renderiza markdown (GFM) como HTML sanitizado.
 *
 * Regra de segurança do projeto: `dangerouslySetInnerHTML` só existe em
 * `components/outputs/*` e sempre recebe a saída de `DOMPurify.sanitize`
 * no mesmo arquivo. O HTML gerado pelo `marked` nunca é injetado cru.
 */
import DOMPurify from "dompurify";
import { Marked } from "marked";
import { memo, useMemo } from "react";
import styles from "./Markdown.module.css";

const md = new Marked({ gfm: true, breaks: false });

/** Markdown → HTML já sanitizado pelo DOMPurify (perfil HTML, sem SVG/MathML). */
export function renderMarkdown(source: string): string {
  return DOMPurify.sanitize(md.parse(source, { async: false }), { USE_PROFILES: { html: true } });
}

export interface MarkdownProps {
  source: string;
  className?: string;
}

export const Markdown = memo(function Markdown({ source, className }: MarkdownProps) {
  const sanitized = useMemo(() => renderMarkdown(source), [source]);
  return (
    <div
      className={className ? `${styles.markdown} ${className}` : styles.markdown}
      dangerouslySetInnerHTML={{ __html: sanitized }}
    />
  );
});
