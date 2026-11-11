/**
 * `display_data`/`execute_result`: escolhe o MIME (HTML > imagem > markdown >
 * texto) e delega ao renderizador. Imagens só como data URL em `<img>` — SVG
 * inclusive (`data:image/svg+xml;base64,...`), nunca SVG inline.
 */
import { memo } from "react";
import type { DisplayDataOutput, ExecuteResultOutput } from "../../api/nbformat";
import { AnsiText } from "./AnsiText";
import { HtmlOutput } from "./HtmlOutput";
import { Markdown } from "./Markdown";
import { pickMime, utf8ToBase64 } from "./mime";
import styles from "./Outputs.module.css";

type BundleOutput = DisplayDataOutput | ExecuteResultOutput;

function imageSize(output: BundleOutput, mime: string): { width?: number; height?: number } {
  const meta = output.metadata?.[mime];
  if (!meta || typeof meta !== "object") return {};
  const { width, height } = meta as { width?: unknown; height?: unknown };
  return {
    width: typeof width === "number" ? width : undefined,
    height: typeof height === "number" ? height : undefined,
  };
}

export const MimeOutput = memo(function MimeOutput({ output }: { output: BundleOutput }) {
  const picked = pickMime(output.data ?? {});
  if (!picked) {
    const mimes = Object.keys(output.data ?? {}).join(", ") || "empty";
    return <p className={styles.unsupported}>Output has no supported representation ({mimes}).</p>;
  }
  const { mime, value } = picked;
  switch (mime) {
    case "text/html":
      return <HtmlOutput html={value} />;
    case "image/png":
    case "image/jpeg":
      return (
        <img
          className={styles.image}
          alt=""
          src={`data:${mime};base64,${value.replace(/\s+/g, "")}`}
          {...imageSize(output, mime)}
        />
      );
    case "image/svg+xml":
      return (
        <img
          className={styles.image}
          alt=""
          src={`data:image/svg+xml;base64,${utf8ToBase64(value)}`}
          {...imageSize(output, mime)}
        />
      );
    case "text/markdown":
      return <Markdown source={value} className={styles.markdown} />;
    case "text/plain":
      return (
        <pre className={styles.pre} data-output-mime="text/plain">
          <AnsiText text={value} />
        </pre>
      );
  }
});
