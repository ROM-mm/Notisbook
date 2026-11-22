/**
 * Settings → Runtimes: DuckDB. Status, extensões do manifesto (instaladas ou não), instalação
 * com progresso ao vivo e remoção. Instalar/remover ficam bloqueados com sessão do kernel aberta.
 */
import { useState } from "react";
import { ApiError, errorMessage } from "../../api/http";
import { JobProgress, type JobLabels } from "./JobProgress";
import { useDuckDBData } from "./useDuckDBData";
import styles from "./Spark.module.css";

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
  const { status, extensions, sessions, job, install, remove, dismissJob } = useDuckDBData();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = status.data;
  const installed = data?.installed ?? null;
  const using = sessions.filter((s) => s.kernel_name === (data?.kernel_name ?? "duckdb"));
  const jobRunning = job?.status === "running" || data?.installing != null;
  const blocked = using.length > 0 || jobRunning || busy;
  const reason = jobRunning
    ? "A DuckDB job is in progress."
    : using.length > 0
      ? `In use by ${using.length === 1 ? "1 open notebook" : `${using.length} open notebooks`}: ${using.map((s) => s.path).join(", ")}. Close the tab first.`
      : undefined;

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

  const onRemove = () => {
    if (!installed) return;
    const msg = `Remove DuckDB ${installed.version}?\n\nThe kernel "${installed.kernel_name}" and the runtime ${installed.env_dir} will be deleted.`;
    if (window.confirm(msg)) void run(remove);
  };

  return (
    <div className={styles.block} data-testid="duckdb-runtime">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>DuckDB</h3>
        {installed ? (
          <span title={reason} className={styles.rowAction}>
            <button
              type="button"
              className={`btn ${styles.dangerBtn}`}
              data-testid="duckdb-remove"
              disabled={blocked}
              aria-label="Remove DuckDB"
              onClick={onRemove}
            >
              {busy ? "Working…" : "Remove"}
            </button>
          </span>
        ) : data?.supported ? (
          <span title={reason} className={styles.rowAction}>
            <button
              type="button"
              className="btn"
              data-testid="duckdb-install"
              disabled={blocked}
              aria-label={`Install DuckDB ${data.version ?? ""}`}
              onClick={() => void run(install)}
            >
              {busy ? "Working…" : `Install${data.version ? ` ${data.version}` : ""}`}
            </button>
          </span>
        ) : null}
      </div>
      {status.error ? <p className={styles.error}>Could not read the DuckDB status: {status.error}</p> : null}
      {!data && status.loading ? <p className={styles.text}>Loading…</p> : null}
      {data && !data.supported ? (
        <p className={styles.notice} data-testid="duckdb-unsupported">
          DuckDB is not available on this platform.
        </p>
      ) : null}
      {data?.supported ? (
        <p className={styles.text} data-testid="duckdb-status">
          {installed ? (
            <>
              Installed: {installed.display_name} <span className={styles.rowKernel}>{installed.kernel_name}</span>
              {using.length > 0 ? <span className={`${styles.tag} ${styles.tagActive}`}>in use</span> : null}
            </>
          ) : (
            `Not installed. Installing sets up DuckDB ${data.version ?? ""} with the extensions below, loaded offline.`
          )}
        </p>
      ) : null}
      {installed ? (
        <p className={styles.rowMeta}>
          <span className={styles.mono} title={installed.env_dir}>
            {installed.env_dir}
          </span>
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
      {extensions.error ? <p className={styles.error}>Could not list the extensions: {extensions.error}</p> : null}
      {extensions.data ? (
        <ul className={styles.rows} data-testid="duckdb-extensions">
          {extensions.data.extensions.map((ext) => (
            <li key={ext.name} className={styles.row} data-extension={ext.name}>
              <div className={styles.rowMain}>
                <div className={styles.rowTitle}>
                  <span className={styles.rowVersion}>{ext.name}</span>
                  <span className={`${styles.tag} ${ext.installed ? styles.tagActive : ""}`}>
                    {ext.installed ? "installed" : "not installed"}
                  </span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
