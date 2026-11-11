/**
 * Área de saídas de uma célula code: agrupa `stream` consecutivos (stdout e
 * stderr) num bloco e delega cada saída ao renderizador do seu tipo.
 */
import { memo, type ReactNode, useMemo } from "react";
import { joinMultiline, type Output } from "../../api/nbformat";
import type { CellLanguage } from "../../state/notebook";
import { ErrorOutput } from "./ErrorOutput";
import { MimeOutput } from "./MimeOutput";
import styles from "./Outputs.module.css";
import { type StreamSegment, StreamOutput } from "./StreamOutput";

type Item = { kind: "streams"; segments: StreamSegment[] } | { kind: "output"; output: Output };

function groupOutputs(outputs: Output[]): Item[] {
  const items: Item[] = [];
  for (const output of outputs) {
    if (output.output_type === "stream") {
      const seg: StreamSegment = { name: output.name === "stderr" ? "stderr" : "stdout", text: joinMultiline(output.text) };
      const last = items[items.length - 1];
      if (last?.kind === "streams") last.segments.push(seg);
      else items.push({ kind: "streams", segments: [seg] });
    } else items.push({ kind: "output", output });
  }
  return items;
}

function renderItem(item: Item, sqlCell: boolean): ReactNode {
  if (item.kind === "streams") return <StreamOutput segments={item.segments} />;
  const { output } = item;
  switch (output.output_type) {
    case "error":
      return <ErrorOutput output={output} sqlCell={sqlCell} />;
    case "display_data":
    case "execute_result":
      return <MimeOutput output={output} />;
    default:
      return null;
  }
}

export interface OutputAreaProps {
  outputs: Output[];
  /** Linguagem da célula; só em Spark SQL (`"sql"`) todo erro vira resumo. */
  language?: CellLanguage;
}

export const OutputArea = memo(function OutputArea({ outputs, language }: OutputAreaProps) {
  const items = useMemo(() => groupOutputs(outputs), [outputs]);
  if (items.length === 0) return null;
  return (
    <div className={styles.area} data-testid="cell-outputs">
      {items.map((item, i) => (
        <div key={i} className={styles.item}>
          {renderItem(item, language === "sql")}
        </div>
      ))}
    </div>
  );
});
