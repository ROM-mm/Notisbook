/**
 * Details de um runtime Docker (somente leitura): Dockerfile, imagem, container, montagens,
 * versões e pacotes gravados na instalação. Stop/Restart são as únicas ações; libs mudam
 * pelo Dockerfile + reinstalação, para o container nunca divergir da imagem.
 * Modal nativo (`showModal`).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDockerDetails } from "../../api/docker";
import { ApiError, errorMessage } from "../../api/http";
import type { DockerRuntime, DockerRuntimeDetails, SessionInfo } from "../../api/types";
import dlg from "../../styles/dialog.module.css";
import styles from "./Spark.module.css";

export function formatBytes(bytes: number | null): string | null {
  if (bytes === null || !Number.isFinite(bytes)) return null;
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

/** Estado do container para a UI; "Docker unavailable" quando o daemon não responde. */
export function containerState(rt: DockerRuntime): string {
  if (!rt.available) return "Docker unavailable";
  if (!rt.container) return "container missing";
  return rt.container.running ? "running" : rt.container.status;
}

/** `detail` do backend já vem em texto pronto; 422 é a lista `{loc, msg}` (campo em `loc`). */
export function dockerError(err: unknown): string {
  if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
    return (err.detail as { loc?: unknown[]; msg?: unknown }[])
      .map((d) => {
        const field = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1] ?? "") : "";
        return field && field !== "body" ? `${field}: ${String(d.msg)}` : String(d.msg);
      })
      .join("; ");
  }
  if (err instanceof ApiError && err.status === 404) return "This Docker runtime no longer exists.";
  return errorMessage(err);
}

/** Imagem base com o digest abreviado (`public.ecr…:5 (@sha256:a54b…)`). */
export function baseImage(rt: DockerRuntime): string {
  const { base_image: base, base_digest: digest } = rt.dockerfile;
  if (!base) return "—";
  return digest ? `${base} (@${digest.slice(0, 19)}…)` : base;
}

interface Props {
  runtime: DockerRuntime;
  connectionsDir: string | null;
  /** Sessões abertas deste runtime: bloqueiam Stop/Restart (o backend também responde 409). */
  sessions: SessionInfo[];
  /** Stop/Restart; recarrega a lista do pai. */
  onAction: (key: string, action: "stop" | "restart") => Promise<void>;
  onClose: () => void;
}

export function DockerDetailsDialog({ runtime, connectionsDir, sessions, onAction, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [details, setDetails] = useState<DockerRuntimeDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState<"stop" | "restart" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const key = runtime.key;

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDetails(await getDockerDetails(key, connectionsDir));
      setError(null);
    } catch (err) {
      setError(dockerError(err));
    } finally {
      setLoading(false);
    }
  }, [key, connectionsDir]);

  useEffect(() => {
    void load();
  }, [load]);

  const rt = details ?? runtime;
  const running = !!rt.container?.running;
  const blockReason = sessions.length > 0 ? `In use by ${sessions.length === 1 ? "1 open notebook" : `${sessions.length} open notebooks`}. Close the tab first.` : rt.busy ? "A job is running for this runtime." : null;
  const packages = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const all = details?.packages ?? [];
    return q ? all.filter((p) => p.name.toLowerCase().includes(q)) : all;
  }, [details, filter]);
  const v = rt.versions;
  const size = formatBytes(rt.image_size);

  const act = async (action: "stop" | "restart") => {
    setActing(action);
    setActionError(null);
    try {
      await onAction(key, action);
      await load();
    } catch (err) {
      setActionError(dockerError(err));
    } finally {
      setActing(null);
    }
  };

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.pkgDialog}`}
      aria-labelledby="docker-details-title"
      data-testid="docker-details-dialog"
      onClose={(e) => e.target === e.currentTarget && onClose()}
      onClick={(e) => e.target === e.currentTarget && ref.current?.close()}
    >
      <div className={dlg.head}>
        <h2 id="docker-details-title" className={dlg.title}>
          {rt.label} · {rt.container_name}
        </h2>
        <button type="button" className="btn btn-ghost" aria-label="Close dialog" onClick={() => ref.current?.close()}>
          ✕
        </button>
      </div>

      <dl className={`${styles.facts} ${styles.dockerFacts}`}>
        <dt>Dockerfile</dt>
        <dd className={styles.mono}>{rt.dockerfile.path}</dd>
        <dt>Base image</dt>
        <dd className={styles.mono}>{baseImage(rt)}</dd>
        <dt>Image</dt>
        <dd>
          <span className={styles.mono}>{rt.image}</span>
          {rt.image_present === null ? null : <span className={styles.subtle}> · {rt.image_present ? `present${size ? ` (${size})` : ""}` : "not built"}</span>}
        </dd>
        <dt>State</dt>
        <dd className={styles.dockerState}>
          <span data-testid="docker-details-state">
            <span className={running ? styles.stateDotRunning : styles.stateDot} data-state={containerState(rt)} aria-hidden="true">
              ●
            </span>{" "}
            {containerState(rt)}
          </span>
          <span title={blockReason ?? "Stop the container"}>
            <button type="button" className="btn" data-testid="docker-details-stop" disabled={!running || !!blockReason || acting !== null} onClick={() => void act("stop")}>
              {acting === "stop" ? "Stopping…" : "Stop"}
            </button>
          </span>
          <span title={blockReason ?? "Restart the container"}>
            <button type="button" className="btn" data-testid="docker-details-restart" disabled={!rt.container || !!blockReason || acting !== null} onClick={() => void act("restart")}>
              {acting === "restart" ? "Restarting…" : "Restart"}
            </button>
          </span>
        </dd>
        <dt>Mounts</dt>
        <dd className={styles.mono}>{rt.mounts?.registered.length ? rt.mounts.registered.join(" · ") : "—"}</dd>
        <dt>Versions</dt>
        <dd>
          {[v.spark && `Spark ${v.spark}`, v.pyspark && `PySpark ${v.pyspark}`, (details?.python ?? v.python) && `Python ${details?.python ?? v.python}`, v.java && `Java ${v.java}`]
            .filter(Boolean)
            .join(" · ") || "—"}
        </dd>
        <dt>Formats</dt>
        <dd>{rt.formats.join(" · ") || "—"}</dd>
      </dl>

      {actionError ? <p className={styles.error}>{actionError}</p> : null}
      {rt.mounts?.stale ? <p className={styles.notice}>The mounted folders differ from the current ones. Recreate the runtime from the Installed list to apply them.</p> : null}

      <div className={styles.pkgToolbar}>
        <h3 className={styles.blockTitle}>Python libraries</h3>
        <span className={styles.footNote}>read-only — they come from the image</span>
        <input
          className={`${styles.input} ${styles.pkgFilter}`}
          type="search"
          placeholder="Filter libraries…"
          aria-label="Filter libraries"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      <div className={styles.pkgScroll}>
        {loading && !details ? <p className={styles.text}>Loading…</p> : null}
        {error ? <p className={styles.error}>Could not load the details: {error}</p> : null}
        {details ? (
          <table className={styles.pkgTable}>
            <thead>
              <tr>
                <th>Library</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {packages.map((p) => (
                <tr key={p.name} data-testid="docker-package-row">
                  <td className={styles.mono}>{p.name}</td>
                  <td>{p.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {details && packages.length === 0 ? <p className={styles.text}>No libraries match.</p> : null}
      </div>

      <p className={styles.notice}>To change the libraries of a Docker runtime, edit the Dockerfile and reinstall. This keeps the container identical to the image.</p>

      <div className={dlg.foot}>
        <span className={styles.footNote}>{details ? `${details.packages.length} libraries` : ""}</span>
        <button type="button" className="btn" onClick={() => ref.current?.close()}>
          Close
        </button>
      </div>
    </dialog>
  );
}
