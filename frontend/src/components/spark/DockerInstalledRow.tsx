/**
 * Linha de um runtime Docker na lista Installed: container, estado e versões, com Config
 * (detalhes e libs, somente leitura) e Remove. Montagens defasadas (ex.: Connections trocada) mostram um aviso
 * com Recriar. Docker parado não quebra a lista: o estado do container fica "unavailable".
 */
import { useState } from "react";
import { ApiError } from "../../api/http";
import type { DockerRuntime, SessionInfo } from "../../api/types";
import { containerState, DockerDetailsDialog, dockerError } from "./DockerDetailsDialog";
import { CategoryTag } from "./RuntimeCombo";
import styles from "./Spark.module.css";

interface Props {
  runtime: DockerRuntime;
  connectionsDir: string | null;
  sessions: SessionInfo[];
  onAction: (key: string, action: "stop" | "restart" | "remove") => Promise<void>;
  onRecreate: (runtime: DockerRuntime) => void;
}

function removeError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409) return `In use: close the notebooks that use this runtime and wait for jobs to finish. (${err.message})`;
  return dockerError(err);
}

export function DockerInstalledRow({ runtime, connectionsDir, sessions, onAction, onRecreate }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const using = sessions.filter((s) => s.kernel_name === runtime.kernel_name);
  const state = containerState(runtime);
  const v = runtime.versions;
  const stale = runtime.mounts?.stale === true;
  const blocked = using.length > 0 || runtime.busy;
  const reason = runtime.busy
    ? "A job is running for this runtime."
    : using.length > 0
      ? `In use by ${using.length === 1 ? "1 open notebook" : `${using.length} open notebooks`}: ${using.map((s) => s.path).join(", ")}. Close the tab first.`
      : null;

  const remove = async () => {
    const msg = `Remove ${runtime.label}?\n\nThe container "${runtime.container_name}" and the kernel registration will be deleted. The image ${runtime.image} is kept, so installing again is fast.`;
    if (!window.confirm(msg)) return;
    setBusy(true);
    setError(null);
    try {
      await onAction(runtime.key, "remove");
    } catch (err) {
      setError(removeError(err));
      setBusy(false);
    }
  };

  const versions = [v.spark && `Spark ${v.spark}`, v.python && `Python ${v.python}`].filter(Boolean);

  return (
    <li className={styles.row} data-testid="docker-runtime-row" data-runtime={runtime.key} data-kernel={runtime.kernel_name}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>
          <span className={styles.rowVersion}>{runtime.label}</span>
          <CategoryTag category="docker" />
          {using.length > 0 ? <span className={`${styles.tag} ${styles.tagActive}`}>in use</span> : null}
          {runtime.busy ? <span className={`${styles.tag} ${styles.tagActive}`}>working</span> : null}
        </div>
        <div className={`${styles.rowMeta} ${styles.mono}`} data-testid="docker-runtime-meta">
          <span>{`container ${runtime.container_name}`}</span>
          <span>
            <span className={state === "running" ? styles.stateDotRunning : styles.stateDot} data-state={state} aria-hidden="true">
              ●
            </span>{" "}
            {state}
          </span>
          {versions.map((m) => (
            <span key={String(m)}>{m}</span>
          ))}
        </div>
        {stale ? (
          <div className={styles.staleBox} data-testid="docker-runtime-stale">
            <span>The container mounts folders that no longer match the current ones (for example, the Connections folder changed). Recreate it to apply them.</span>
            <span title={reason ?? "Recreate the container with the current folders"}>
              <button type="button" className="btn" data-testid="docker-runtime-recreate" disabled={blocked || busy || !runtime.available} onClick={() => onRecreate(runtime)}>
                Recreate
              </button>
            </span>
          </div>
        ) : null}
        {!stale && runtime.mounts?.error ? <p className={styles.notice}>Current folders cannot be mounted: {runtime.mounts.error}</p> : null}
        {error ? (
          <p className={styles.error} data-testid="docker-remove-error">
            {error}
          </p>
        ) : null}
      </div>
      <span className={styles.rowActions}>
        <span title={`Configuration of ${runtime.label} (read-only)`} className={styles.rowAction}>
          <button type="button" className="btn" data-testid="docker-runtime-config" disabled={busy} aria-label={`Configuration of ${runtime.label}`} onClick={() => setDetailsOpen(true)}>
            Config
          </button>
        </span>
        <span title={reason ?? `Remove ${runtime.label} (the image is kept)`} className={styles.rowAction}>
          <button
            type="button"
            className={`btn ${styles.dangerBtn}`}
            data-testid="docker-runtime-remove"
            disabled={blocked || busy || !runtime.available}
            aria-label={`Remove ${runtime.label}`}
            onClick={() => void remove()}
          >
            {busy ? "Removing…" : "Remove"}
          </button>
        </span>
      </span>
      {detailsOpen ? (
        <DockerDetailsDialog runtime={runtime} connectionsDir={connectionsDir} sessions={using} onAction={onAction} onClose={() => setDetailsOpen(false)} />
      ) : null}
    </li>
  );
}
