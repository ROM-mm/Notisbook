/**
 * Progresso ao vivo de um job: barra (`progress`), fase atual, log rolável e estado final.
 * Por padrão descreve a instalação de uma versão; `labels` e `title` adaptam o texto a outros jobs
 * e `indeterminate` esconde a porcentagem quando o job não informa progresso.
 */
import { useEffect, useRef } from "react";
import type { InstallJob } from "./useSparkData";
import styles from "./Spark.module.css";

const PHASE_LABEL: Record<string, string> = {
  prereqs: "Checking prerequisites",
  python: "Preparing Python",
  venv: "Creating virtual environment",
  install: "Installing packages",
  validate: "Validating installation",
  kernelspec: "Registering kernel",
  cleanup: "Cleaning up",
};

export interface JobLabels {
  running?: string;
  succeeded: string;
  failed: string;
  log: string;
}

const INSTALL_LABELS: JobLabels = {
  succeeded: "Installation complete",
  failed: "Installation failed",
  log: "Installation log",
};

function statusText(job: InstallJob, labels: JobLabels): string {
  switch (job.status) {
    case "running":
      return labels.running ?? (job.phase ? (PHASE_LABEL[job.phase] ?? job.phase) : "Starting…");
    case "succeeded":
      return labels.succeeded;
    case "failed":
      return labels.failed;
    case "lost":
      return "Tracking interrupted";
  }
}

interface Props {
  job: InstallJob;
  onDismiss?: () => void;
  title?: string;
  labels?: JobLabels;
  indeterminate?: boolean;
}

export function JobProgress({ job, onDismiss, title, labels = INSTALL_LABELS, indeterminate = false }: Props) {
  const logRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = logRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [job.lines.length]);

  const pct = Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
  const failMessage = job.status === "failed" || job.status === "lost" ? (job.message ?? "").replace(/^failed:\s*/, "") : "";

  return (
    <div className={styles.job} data-testid="spark-job" data-status={job.status} data-job={job.id}>
      <div className={styles.jobHead}>
        <span className={styles.jobTitle}>{title ?? `Spark ${job.version ?? "…"}`}</span>
        <span className={`${styles.jobStatus} ${styles[`js_${job.status}`] ?? ""}`} data-testid="spark-job-status">
          {job.status === "running" ? <span className={styles.spinner} aria-hidden="true" /> : null}
          {statusText(job, labels)}
        </span>
        {indeterminate ? null : <span className={styles.jobPct}>{pct}%</span>}
        {job.status !== "running" && onDismiss ? (
          <button type="button" className="btn btn-ghost" onClick={onDismiss} aria-label="Close installation panel">
            Close
          </button>
        ) : null}
      </div>
      <div
        className={styles.bar}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate && job.status === "running" ? undefined : pct}
        aria-label={title ?? `Spark installation ${job.version ?? ""}`}
      >
        <div
          className={`${styles.barFill} ${styles[`bar_${job.status}`] ?? ""} ${indeterminate && job.status === "running" ? styles.barIndeterminate : ""}`}
          style={{ width: indeterminate && job.status === "running" ? "40%" : `${pct}%` }}
        />
      </div>
      {failMessage ? (
        <p className={styles.error} data-testid="spark-job-error">
          {failMessage}
        </p>
      ) : null}
      <div
        ref={logRef}
        className={styles.log}
        data-testid="spark-job-log"
        tabIndex={0}
        aria-label={labels.log}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        }}
      >
        {job.lines.length === 0 ? <div className={styles.subtle}>Waiting for events…</div> : null}
        {job.lines.map((l, i) => (
          <div key={i} className={styles.logLine}>
            <span className={styles.logPhase}>{l.phase}</span>
            <span className={styles.logText}>{l.line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
