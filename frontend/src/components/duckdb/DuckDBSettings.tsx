/**
 * Settings → Runtimes: DuckDB. Versões do catálogo (com as extensões de cada uma), instalação
 * com progresso ao vivo e remoção. Instalar/remover ficam bloqueados com sessão do kernel aberta.
 */
import { useState } from "react";
import { ApiError, errorMessage } from "../../api/http";
import { JobProgress, type JobLabels } from "../spark/JobProgress";
import { useDuckDBData } from "./useDuckDBData";
import styles from "../spark/Spark.module.css";

const LABELS: JobLabels = {
  succeeded: "Installation complete",
  failed: "Installation failed",
  log: "DuckDB installation log",
};

function actionError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409)
    return `In use: close the notebooks that use this runtime (or wait for the job to finish). (${err.message})`;
  if (err instanceof ApiError && err.status === 404) return "DuckDB is no longer installed.";
  if (err instanceof ApiError && err.status === 422) return `Not available on this platform. (${err.message})`;
  if (err instanceof ApiError && err.status === 500)
    return `The runtime was not fully removed. ${err.message}. Delete what is left manually and try again.`;
  return errorMessage(err);
}

export function DuckDBSettings() {
  const { status, sessions, job, install, remove, dismissJob } = useDuckDBData();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = status.data;
  const jobRunning = job?.status === "running" || (data?.installing.length ?? 0) > 0;

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  const onRemove = (version: string) => {
    const item = data?.installed.find((i) => i.version === version);
    if (!item) return;
    const msg = `Remove DuckDB ${item.version}?\n\nThe kernel "${item.kernel_name}" and the runtime ${item.env_dir} will be deleted.`;
    if (window.confirm(msg)) void run(() => remove(version));
  };

  return (
    <div className={styles.block} data-testid="duckdb-runtime">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>DuckDB</h3>
      </div>
      {status.error ? <p className={styles.error}>Could not read the DuckDB status: {status.error}</p> : null}
      {!data && status.loading ? <p className={styles.text}>Loading…</p> : null}
      {data && !data.supported ? (
        <p className={styles.notice} data-testid="duckdb-unsupported">
          DuckDB is not available on this platform.
        </p>
      ) : null}
      {error ? (
        <p className={styles.error} data-testid="duckdb-error">
          {error}
        </p>
      ) : null}
      {job ? (
        <div className={styles.jobs} aria-live="polite" data-testid="duckdb-job">
          <JobProgress job={job} title={`DuckDB ${job.version ?? ""}`.trim()} labels={LABELS} onDismiss={dismissJob} />
        </div>
      ) : null}
      {data?.supported ? (
        <ul className={styles.rows}>
          {data.catalog.map((item) => {
            const installed = data.installed.find((i) => i.version === item.version);
            const using = installed ? sessions.filter((s) => s.kernel_name === installed.kernel_name) : [];
            const blocked = using.length > 0 || jobRunning || busy;
            return (
              <li key={item.version} className={styles.row} data-version={item.version}>
                <div className={styles.rowMain}>
                  <div className={styles.rowTitle}>
                    <span className={styles.rowVersion}>DuckDB {item.version}</span>
                    {installed ? <span className={styles.rowKernel}>{installed.kernel_name}</span> : null}
                  </div>
                  <div className={styles.rowMeta}>{item.extensions.join(" · ")}</div>
                </div>
                <span className={styles.rowAction}>
                  {installed ? (
                    <button type="button" className={`btn ${styles.dangerBtn}`} disabled={blocked} onClick={() => onRemove(item.version)}>
                      Remove
                    </button>
                  ) : (
                    <button type="button" className="btn" disabled={blocked} onClick={() => void run(() => install(item.version))}>
                      Install
                    </button>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
