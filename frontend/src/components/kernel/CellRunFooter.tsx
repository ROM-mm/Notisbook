/**
 * Rodapé de execução por célula (discreto à la Databricks): status,
 * `execution_count` e duração medida no frontend (envio do `execute` →
 * `execute_reply`) em `[data-testid="cell-duration"]`, formato `1.02 s`.
 */
import { memo, useEffect, useState } from "react";
import { type CellRun, formatDuration } from "../../state/kernel";
import { useKernel } from "../../state/notebookContext";
import { CheckSmallIcon, CrossSmallIcon } from "./icons";
import styles from "./Kernel.module.css";

function Elapsed({ startedAt }: { startedAt: number }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 100);
    return () => clearInterval(t);
  }, []);
  return <span data-testid="cell-elapsed">{formatDuration(performance.now() - startedAt)}</span>;
}

function timeOfDay(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

const LABEL: Record<CellRun["status"], string> = {
  queued: "Queued",
  running: "Running",
  ok: "Completed",
  error: "Error",
  aborted: "Cancelled",
};

export const CellRunFooter = memo(function CellRunFooter({ cellId }: { cellId: string }) {
  const run = useKernel((s) => s.runs[cellId]);
  if (!run) return null;
  const { status } = run;

  return (
    <div className={`${styles.footer} ${styles[`f_${status}`]}`} data-testid="cell-footer" data-status={status}>
      <span className={styles.footerStatus}>
        {status === "running" || status === "queued" ? <span className={styles.spinner} aria-hidden="true" /> : null}
        {status === "ok" ? <CheckSmallIcon /> : null}
        {status === "error" ? <CrossSmallIcon /> : null}
        {LABEL[status]}
      </span>
      {run.executionCount !== null ? <span className={styles.sep}>[{run.executionCount}]</span> : null}
      {status === "running" && run.startedAt !== null ? (
        <span className={styles.sep}>
          <Elapsed startedAt={run.startedAt} />
        </span>
      ) : null}
      {run.durationMs !== null ? (
        <span className={styles.sep}>
          <span data-testid="cell-duration">{formatDuration(run.durationMs)}</span>
        </span>
      ) : null}
      {run.finishedAt !== null ? <span className={styles.sep}>at {timeOfDay(run.finishedAt)}</span> : null}
      {run.note ? (
        <span className={`${styles.sep} ${styles.note}`} data-testid="cell-note">
          {run.note}
        </span>
      ) : null}
    </div>
  );
});
