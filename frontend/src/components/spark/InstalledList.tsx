/**
 * Lista Installed unificada, na ordem das categorias: Data processing (Spark local,
 * `GET /api/spark/versions`), Analytics (DuckDB por versão, `GET /api/duckdb`) e Docker (Glue).
 *
 * - Cada linha traz o rótulo da categoria e o botão Config: Spark e DuckDB abrem o diálogo de
 *   libs (PackagesDialog, com o adaptador de rotas de cada um; no DuckDB, também as extensões
 *   da versão); Glue abre os detalhes somente leitura do container.
 * - "Remove" pede confirmação; fica desabilitado enquanto houver sessão de kernel ativa ou
 *   job do ambiente (o backend também responde 409, e a mensagem dele é mostrada).
 */
import { useEffect, useMemo, useState } from "react";
import { getDuckDBExtensions } from "../../api/duckdb";
import { ApiError, errorMessage } from "../../api/http";
import type { DockerRuntime, DockerRuntimes, DuckDBExtensions, DuckDBStatus, InstalledDuckDB, InstalledSpark, SessionInfo, SparkVersions } from "../../api/types";
import { DockerInstalledRow } from "./DockerInstalledRow";
import { PackagesDialog } from "./PackagesDialog";
import { CategoryTag } from "./RuntimeCombo";
import { duckdbPackages, sparkPackages } from "./usePackages";
import type { Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

interface Props {
  versions: Loadable<SparkVersions>;
  duckdb: Loadable<DuckDBStatus>;
  docker: Loadable<DockerRuntimes>;
  connectionsDir: string | null;
  sessions: SessionInfo[];
  onRemove: (version: string) => Promise<void>;
  onRemoveDuckDB: (version: string) => Promise<void>;
  onDockerAction: (key: string, action: "stop" | "restart" | "remove") => Promise<void>;
  onDockerRecreate: (runtime: DockerRuntime) => void;
}

function removeError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409)
    return `In use: close the notebooks that use this runtime (or wait for the installation to finish). (${err.message})`;
  if (err instanceof ApiError && err.status === 404) return "This version is no longer installed.";
  if (err instanceof ApiError && err.status === 500)
    return `The runtime was not fully removed. ${err.message}. Delete what is left manually and try again.`;
  return errorMessage(err);
}

const inUse = (using: SessionInfo[]) => (using.length === 1 ? "1 open notebook" : `${using.length} open notebooks`);

/** Confirmação + remoção com estado de "Removing…" e erro por linha. */
function useRemove(onRemove: () => Promise<void>, confirmText: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    if (!window.confirm(confirmText)) return;
    setBusy(true);
    setError(null);
    try {
      await onRemove();
    } catch (err) {
      setError(removeError(err));
      setBusy(false);
    }
  };
  return { busy, error, remove };
}

function SparkRow({ item, sessions, installing, installingVersion, onRemove }: { item: InstalledSpark; sessions: SessionInfo[]; installing: boolean; installingVersion: boolean; onRemove: Props["onRemove"] }) {
  const { busy, error, remove } = useRemove(
    () => onRemove(item.version),
    `Remove Spark ${item.version}?\n\nThe kernel "${item.kernel_name}" and the runtime ${item.env_dir ?? ""} will be deleted.`,
  );
  const [configOpen, setConfigOpen] = useState(false);
  const adapter = useMemo(() => sparkPackages(item.version), [item.version]);
  const using = sessions.filter((s) => s.kernel_name === item.kernel_name);
  const blocked = using.length > 0 || installing;
  const reason = installing
    ? "Installation in progress for this kernel."
    : using.length > 0
      ? `In use by ${inUse(using)}: ${using.map((s) => s.path).join(", ")}. Close the tab to remove it.`
      : `Remove Spark ${item.version}`;
  const configReason = installingVersion
    ? "A job is running for this runtime."
    : using.length > 0
      ? `In use by ${inUse(using)}. Close the tab to change its libraries.`
      : `Libraries of Spark ${item.version}`;

  return (
    <li className={styles.row} data-testid="spark-version-row" data-version={item.version} data-kernel={item.kernel_name}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>
          <span className={styles.rowVersion}>Spark {item.version}</span>
          <CategoryTag category="processing" />
          <span className={styles.rowKernel}>{item.kernel_name}</span>
          {item.legacy ? (
            <span className={styles.tag} title="Runtime created outside Notisbook (.venv-spark*)">
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
            This runtime predates the persistent catalog. Remove it and reinstall Spark {item.version} to enable it.
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
      {configOpen ? (
        <PackagesDialog title={`Spark ${item.version}`} version={item.version} envDir={item.env_dir} adapter={adapter} sessions={using} onClose={() => setConfigOpen(false)} />
      ) : null}
    </li>
  );
}

/** Extensões do manifesto da versão (somente leitura), no topo do Config do DuckDB. */
function DuckDBExtensionsTable({ version }: { version: string }) {
  const [data, setData] = useState<DuckDBExtensions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getDuckDBExtensions(version, ctrl.signal)
      .then(setData)
      .catch((err: unknown) => !ctrl.signal.aborted && setError(errorMessage(err)));
    return () => ctrl.abort();
  }, [version]);

  if (error) return <p className={styles.error}>Could not list the extensions: {error}</p>;
  if (!data) return null;
  return (
    <table className={styles.pkgTable} data-testid="duckdb-extensions">
      <thead>
        <tr>
          <th>Extension</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {data.extensions.map((ext) => (
          <tr key={ext.name} data-extension={ext.name}>
            <td className={styles.mono}>{ext.name}</td>
            <td>{ext.installed ? "✓ installed" : "not installed"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DuckDBRow({ item, sessions, installing, installingVersion, onRemove }: { item: InstalledDuckDB; sessions: SessionInfo[]; installing: boolean; installingVersion: boolean; onRemove: Props["onRemoveDuckDB"] }) {
  const { busy, error, remove } = useRemove(
    () => onRemove(item.version),
    `Remove DuckDB ${item.version}?\n\nThe kernel "${item.kernel_name}" and the runtime ${item.env_dir} will be deleted.`,
  );
  const [configOpen, setConfigOpen] = useState(false);
  const adapter = useMemo(() => duckdbPackages(item.version), [item.version]);
  const using = sessions.filter((s) => s.kernel_name === item.kernel_name);
  const blocked = using.length > 0 || installing;
  const reason = installing
    ? "A job is running for this runtime."
    : using.length > 0
      ? `In use by ${inUse(using)}: ${using.map((s) => s.path).join(", ")}. Close the tab first.`
      : `Remove DuckDB ${item.version}`;
  const configReason = installingVersion
    ? "Installation in progress for this kernel."
    : using.length > 0
      ? `In use by ${inUse(using)}. Close the tab to change its libraries.`
      : `Libraries and extensions of DuckDB ${item.version}`;

  return (
    <li className={styles.row} data-testid="duckdb-version-row" data-version={item.version} data-kernel={item.kernel_name}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>
          <span className={styles.rowVersion}>DuckDB {item.version}</span>
          <CategoryTag category="analytics" />
          <span className={styles.rowKernel}>{item.kernel_name}</span>
          {using.length > 0 ? <span className={`${styles.tag} ${styles.tagActive}`}>in use</span> : null}
        </div>
        <div className={styles.rowMeta}>
          <span>{item.extensions.join(" · ") || item.display_name}</span>
          <span className={styles.mono} title={item.env_dir}>
            {item.env_dir}
          </span>
        </div>
        {error ? (
          <p className={styles.error} data-testid="duckdb-remove-error">
            {error}
          </p>
        ) : null}
      </div>
      <span className={styles.rowActions}>
        <span title={configReason} className={styles.rowAction}>
          <button
            type="button"
            className="btn"
            data-testid="duckdb-version-config"
            disabled={using.length > 0 || installingVersion || busy}
            aria-label={`Configure DuckDB ${item.version}`}
            onClick={() => setConfigOpen(true)}
          >
            Config
          </button>
        </span>
        <span title={reason} className={styles.rowAction}>
          <button
            type="button"
            className={`btn ${styles.dangerBtn}`}
            data-testid="duckdb-version-remove"
            disabled={blocked || busy}
            aria-label={`Remove DuckDB ${item.version}`}
            onClick={() => void remove()}
          >
            {busy ? "Removing…" : "Remove"}
          </button>
        </span>
      </span>
      {configOpen ? (
        <PackagesDialog title={`DuckDB ${item.version}`} version={item.version} envDir={item.env_dir} adapter={adapter} sessions={using} onClose={() => setConfigOpen(false)}>
          <DuckDBExtensionsTable version={item.version} />
        </PackagesDialog>
      ) : null}
    </li>
  );
}

export function InstalledList({ versions, duckdb, docker, connectionsDir, sessions, onRemove, onRemoveDuckDB, onDockerAction, onDockerRecreate }: Props) {
  const data = versions.data;
  const duckInstalled = duckdb.data?.installed ?? [];
  const dockerInstalled = (docker.data?.runtimes ?? []).filter((r) => r.installed);
  const installing = new Set((data?.installing ?? []).map((i) => i.kernel_name));
  const installingVersion = new Set((data?.installing ?? []).filter((i) => i.kind === "install").map((i) => i.kernel_name));
  const duckBusy = new Set((duckdb.data?.installing ?? []).map((i) => i.kernel_name));
  const duckInstalling = new Set((duckdb.data?.installing ?? []).filter((i) => i.kind === "duckdb-install").map((i) => i.kernel_name));
  const empty = (data?.installed.length ?? 0) === 0 && duckInstalled.length === 0 && dockerInstalled.length === 0;
  const loading = !data && versions.loading;
  return (
    <div className={styles.block} data-testid="spark-installed">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>Installed</h3>
      </div>
      {versions.error ? <p className={styles.error}>Could not list the Spark versions: {versions.error}</p> : null}
      {duckdb.error ? <p className={styles.error}>Could not list the DuckDB versions: {duckdb.error}</p> : null}
      {docker.error ? <p className={styles.error}>Could not list the Docker runtimes: {docker.error}</p> : null}
      {docker.data && !docker.data.available ? (
        <p className={styles.notice} data-testid="docker-unavailable">
          Docker is not available (start Colima or Docker Desktop). Docker runtimes cannot be checked or used until it is running.
        </p>
      ) : null}
      {loading ? <p className={styles.text}>Loading…</p> : null}
      {!loading && empty ? <p className={styles.text}>No runtimes installed yet.</p> : null}
      {!empty ? (
        <ul className={styles.rows}>
          {(data?.installed ?? []).map((item) => (
            <SparkRow
              key={item.kernel_name}
              item={item}
              sessions={sessions}
              installing={installing.has(item.kernel_name)}
              installingVersion={installingVersion.has(item.kernel_name)}
              onRemove={onRemove}
            />
          ))}
          {duckInstalled.map((item) => (
            <DuckDBRow key={item.kernel_name} item={item} sessions={sessions} installing={duckBusy.has(item.kernel_name)} installingVersion={duckInstalling.has(item.kernel_name)} onRemove={onRemoveDuckDB} />
          ))}
          {dockerInstalled.map((rt) => (
            <DockerInstalledRow key={rt.key} runtime={rt} connectionsDir={connectionsDir} sessions={sessions} onAction={onDockerAction} onRecreate={onDockerRecreate} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
