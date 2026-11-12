/**
 * Status de execução por célula, solto sob a caixa de código: `✓ 1.02 s`,
 * `✗ Error`, etc. A duração (medida no frontend, envio do `execute` →
 * `execute_reply`) fica em `[data-testid="cell-duration"]`.
 */
import { memo, useEffect, useState } from "react";
import { type CellRun, formatDuration } from "../../state/kernel";
import { useKernel } from "../../state/notebookContext";
import styles from "../notebook/Notebook.module.css";

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

const GLYPH: Record<CellRun["status"], string> = {
  queued: "…",
  running: "…",
  ok: "✓",
  error: "✗",
  aborted: "✗",
};

const STATUS_CLASS: Record<CellRun["status"], string | undefined> = {
  queued: styles.runQueued,
  running: styles.runRunning,
  ok: styles.runOk,
  error: styles.runError,
  aborted: styles.runAborted,
};

export const CellRunFooter = memo(function CellRunFooter({ cellId }: { cellId: string }) {
  const run = useKernel((s) => s.runs[cellId]);
  if (!run) return null;
  const { status } = run;
  // Com sucesso e duração conhecida, o tempo substitui o rótulo ("✓ 1.02 s").
  const durationAsMain = status === "ok" && run.durationMs !== null;

  return (
    <div className={`${styles.runStatus} ${STATUS_CLASS[status]}`} data-testid="cell-footer" data-status={status}>
      <span className={styles.runMain}>
        <span className={styles.runGlyph} aria-hidden="true">
          {GLYPH[status]}
        </span>
        {durationAsMain ? <span data-testid="cell-duration">{formatDuration(run.durationMs ?? 0)}</span> : LABEL[status]}
      </span>
      {status === "running" && run.startedAt !== null ? (
        <span className={styles.runSep}>
          <Elapsed startedAt={run.startedAt} />
        </span>
      ) : null}
      {!durationAsMain && run.durationMs !== null ? (
        <span className={styles.runSep}>
          <span data-testid="cell-duration">{formatDuration(run.durationMs)}</span>
        </span>
      ) : null}
      {run.finishedAt !== null ? <span className={styles.runSep}>at {timeOfDay(run.finishedAt)}</span> : null}
      {run.note ? (
        <span className={`${styles.runSep} ${styles.runNote}`} data-testid="cell-note">
          {run.note}
        </span>
      ) : null}
    </div>
  );
});
