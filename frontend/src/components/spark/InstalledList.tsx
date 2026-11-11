/**
 * Versões instaladas (`GET /api/spark/versions`). "Remover" pede confirmação e
 * chama `DELETE /api/spark/versions/{v}`; fica desabilitado enquanto houver
 * sessão de kernel ativa daquela versão (o backend também responde 409).
 * "Config" abre o diálogo de libs do ambiente, com o mesmo bloqueio.
 */
import { useState } from "react";
import { ApiError, errorMessage } from "../../api/http";
import type { InstalledSpark, SessionInfo, SparkVersions } from "../../api/types";
import { PackagesDialog } from "./PackagesDialog";
import type { Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

interface Props {
  versions: Loadable<SparkVersions>;
  sessions: SessionInfo[];
  onRemove: (version: string) => Promise<void>;
}

function removeError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409)
    return `In use: close the notebooks that use this environment (or wait for the installation to finish). (${err.message})`;
  if (err instanceof ApiError && err.status === 404) return "This version is no longer installed.";
  if (err instanceof ApiError && err.status === 500)
    return `The environment was not fully removed. ${err.message}. Delete what is left manually and try again.`;
  return errorMessage(err);
}

function Row({ item, sessions, installing, installingVersion, onRemove }: { item: InstalledSpark; sessions: SessionInfo[]; installing: boolean; installingVersion: boolean; onRemove: Props["onRemove"] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const using = sessions.filter((s) => s.kernel_name === item.kernel_name);
  const blocked = using.length > 0 || installing;
  const reason = installing
    ? "Installation in progress for this kernel."
    : using.length > 0
      ? `In use by ${using.length === 1 ? "1 open notebook" : `${using.length} open notebooks`}: ${using.map((s) => s.path).join(", ")}. Close the tab to remove it.`
      : `Remove Spark ${item.version}`;
  const configReason = installingVersion
    ? "A job is running for this environment."
    : using.length > 0
      ? `In use by ${using.length === 1 ? "1 open notebook" : `${using.length} open notebooks`}. Close the tab to change its libraries.`
      : `Libraries of Spark ${item.version}`;

  const remove = async () => {
    const msg = `Remove Spark ${item.version}?\n\nThe kernel "${item.kernel_name}" and the environment ${item.env_dir ?? ""} will be deleted.`;
    if (!window.confirm(msg)) return;
    setBusy(true);
    setError(null);
    try {
      await onRemove(item.version);
    } catch (err) {
      setError(removeError(err));
      setBusy(false);
    }
  };

  return (
    <li className={styles.row} data-testid="spark-version-row" data-version={item.version} data-kernel={item.kernel_name}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>
          <span className={styles.rowVersion}>Spark {item.version}</span>
          <span className={styles.rowKernel}>{item.kernel_name}</span>
          {item.legacy ? (
            <span className={styles.tag} title="Environment created outside Notisbook (.venv-spark*)">
              legacy
            </span>
          ) : null}
          {using.length > 0 ? <span className={`${styles.tag} ${styles.tagActive}`}>in use</span> : null}
        </div>
        <div className={styles.rowMeta}>
          <span>{item.display_name}</span>
          {item.env_dir ? <span className={styles.mono} title={item.env_dir}>{item.env_dir}</span> : null}
        </div>
        {item.bundle_status === "outdated" ? (
          <p className={styles.error} data-testid="spark-version-outdated">
            This environment predates the persistent catalog. Remove it and reinstall Spark {item.version} to enable it.
          </p>
        ) : null}
        {error ? (
          <p className={styles.error} data-testid="spark-remove-error">
            {error}
          </p>
        ) : null}
      </div>
      <span className={styles.rowActions}>
        <span title={configReason} className={styles.rowAction}>
          <button
            type="button"
            className="btn"
            data-testid="spark-version-config"
            disabled={using.length > 0 || installingVersion || busy}
            aria-label={`Configure libraries of Spark ${item.version}`}
            onClick={() => setConfigOpen(true)}
          >
            Config
          </button>
        </span>
        <span title={reason} className={styles.rowAction}>
        <button
          type="button"
          className={`btn ${styles.dangerBtn}`}
          data-testid="spark-version-remove"
          disabled={blocked || busy}
          aria-label={`Remove Spark ${item.version}`}
          onClick={() => void remove()}
        >
          {busy ? "Removing…" : "Remove"}
        </button>
        </span>
      </span>
      {configOpen ? <PackagesDialog version={item.version} envDir={item.env_dir} sessions={using} onClose={() => setConfigOpen(false)} /> : null}
    </li>
  );
}

export function InstalledList({ versions, sessions, onRemove }: Props) {
  const data = versions.data;
  const installing = new Set((data?.installing ?? []).map((i) => i.kernel_name));
  const installingVersion = new Set((data?.installing ?? []).filter((i) => i.kind === "install").map((i) => i.kernel_name));
  return (
    <div className={styles.block} data-testid="spark-installed">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>Installed</h3>
      </div>
      {versions.error ? <p className={styles.error}>Could not list the versions: {versions.error}</p> : null}
      {data && data.installed.length === 0 ? <p className={styles.text}>No versions installed yet.</p> : null}
      {!data && versions.loading ? <p className={styles.text}>Loading…</p> : null}
      {data && data.installed.length > 0 ? (
        <ul className={styles.rows}>
          {data.installed.map((item) => (
            <Row key={item.kernel_name} item={item} sessions={sessions} installing={installing.has(item.kernel_name)} installingVersion={installingVersion.has(item.kernel_name)} onRemove={onRemove} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
