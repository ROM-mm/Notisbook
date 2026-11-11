/** Texto com códigos ANSI (stream, text/plain, traceback) → HTML escapado e sanitizado. */
import DOMPurify from "dompurify";
import { memo, useMemo } from "react";
import { ansiToHtml } from "./ansi";
import { ANSI_CONFIG } from "./purify";

export interface AnsiTextProps {
  text: string;
  className?: string;
}

/** `<span>` inline; quem usa decide o contêiner (`<pre>`). */
export const AnsiText = memo(function AnsiText({ text, className }: AnsiTextProps) {
  const html = useMemo(() => DOMPurify.sanitize(ansiToHtml(text), ANSI_CONFIG), [text]);
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
});
