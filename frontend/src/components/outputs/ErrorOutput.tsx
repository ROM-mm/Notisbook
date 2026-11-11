/**
 * Saída `error`. Erro do Spark: resumo (tipo, classe, mensagem, causa) com o
 * traceback completo em "show details". Demais erros: traceback ANSI → HTML
 * escapado (ansi_up) + DOMPurify; sem `ESC[` no DOM.
 */
import DOMPurify from "dompurify";
import { memo, useMemo } from "react";
import type { ErrorOutput as ErrorOutputData } from "../../api/nbformat";
import { ansiToHtml } from "./ansi";
import styles from "./Outputs.module.css";
import { ANSI_CONFIG } from "./purify";
import { isSparkError, type RootCause, summarizeSparkError } from "./sparkError";

function Cause({ label, cause }: { label: string; cause: RootCause }) {
  return (
    <p className={styles.errCause}>
      {label}: <abbr title={cause.fqcn}>{cause.name}</abbr>
      {cause.message ? `: ${cause.message}` : ""}
    </p>
  );
}

export const ErrorOutput = memo(function ErrorOutput({
  output,
  sqlCell = false,
}: {
  output: ErrorOutputData;
  /** Célula SQL: todo erro vira resumo. */
  sqlCell?: boolean;
}) {
  const traceback = useMemo(() => (Array.isArray(output.traceback) ? output.traceback : []), [output]);
  const html = useMemo(() => {
    const text = traceback.length > 0 ? traceback.join("\n") : `${output.ename}: ${output.evalue}`;
    return DOMPurify.sanitize(ansiToHtml(text), ANSI_CONFIG);
  }, [output, traceback]);
  const summary = useMemo(
    () => (isSparkError(output.ename, traceback, sqlCell) ? summarizeSparkError(output.ename, output.evalue) : null),
    [output, traceback, sqlCell],
  );
  const full = <pre className={styles.pre} dangerouslySetInnerHTML={{ __html: html }} />;

  if (!summary) {
    return (
      <div className={styles.error} data-output-type="error" role="alert">
        {full}
      </div>
    );
  }
  const meta = [summary.sqlState && `SQLSTATE ${summary.sqlState}`, summary.position].filter(Boolean).join(" · ");
  return (
    <div className={styles.error} data-output-type="error" data-spark-error="" role="alert">
      <div className={styles.errHead}>
        <span className={styles.errName}>{output.ename}</span>
        {summary.errorClass && <span className={styles.errChip}>[{summary.errorClass}]</span>}
      </div>
      {summary.message && <p className={styles.errMsg}>{summary.message}</p>}
      {summary.rootCause && <Cause label="Cause" cause={summary.rootCause} />}
      {summary.topException && <Cause label="Exception" cause={summary.topException} />}
      {meta && <p className={styles.errMeta}>{meta}</p>}
      <details className={styles.errDetails}>
        <summary>show details</summary>
        {full}
      </details>
    </div>
  );
});
