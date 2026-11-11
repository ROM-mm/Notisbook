/**
 * Saídas `stream` consecutivas (stdout e stderr intercalados) num único bloco
 * pré-formatado: `\r` aplicado como num terminal, ANSI convertido e saídas
 * longas colapsadas com "mostrar mais".
 */
import { memo, useMemo, useState } from "react";
import { applyCarriageReturns } from "./ansi";
import { AnsiText } from "./AnsiText";
import styles from "./Outputs.module.css";

export interface StreamSegment {
  name: "stdout" | "stderr";
  text: string;
}

/** Linhas visíveis antes de colapsar. */
const COLLAPSED_LINES = 150;

function countLines(text: string): number {
  let n = 1;
  for (let i = 0; i < text.length; i += 1) if (text.charCodeAt(i) === 10) n += 1;
  return text.endsWith("\n") ? n - 1 : n;
}

/** Corta os segmentos em `limit` linhas no total. */
function truncate(segments: StreamSegment[], limit: number): StreamSegment[] {
  const out: StreamSegment[] = [];
  let budget = limit;
  for (const seg of segments) {
    if (budget <= 0) break;
    const n = countLines(seg.text);
    if (n <= budget) {
      out.push(seg);
      budget -= n;
      continue;
    }
    out.push({ name: seg.name, text: `${seg.text.split("\n").slice(0, budget).join("\n")}\n` });
    budget = 0;
  }
  return out;
}

export const StreamOutput = memo(function StreamOutput({ segments }: { segments: StreamSegment[] }) {
  const [expanded, setExpanded] = useState(false);
  const processed = useMemo(
    () => segments.map((s) => ({ name: s.name, text: applyCarriageReturns(s.text) })),
    [segments],
  );
  const total = useMemo(() => processed.reduce((n, s) => n + countLines(s.text), 0), [processed]);
  const collapsible = total > COLLAPSED_LINES;
  const visible = collapsible && !expanded ? truncate(processed, COLLAPSED_LINES) : processed;

  return (
    <div className={styles.stream} data-output-type="stream">
      <pre className={styles.pre}>
        {visible.map((s, i) => (
          <AnsiText key={i} text={s.text} className={s.name === "stderr" ? styles.stderr : undefined} />
        ))}
      </pre>
      {collapsible ? (
        <button type="button" className={styles.more} onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Show less" : `Show more (${total - COLLAPSED_LINES} hidden lines)`}
        </button>
      ) : null}
    </div>
  );
});
