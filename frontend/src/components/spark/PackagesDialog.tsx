/**
 * Config de um ambiente Spark: lista as libs (base incluída) e permite adicionar (＋),
 * desinstalar (−) e atualizar (↑) as marcadas. PyPI apenas.
 *
 * Modal nativo (`showModal`). Durante um job fica travado: Esc/Close/backdrop não fecham e,
 * se o navegador fechar mesmo assim, o diálogo reabre.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, errorMessage } from "../../api/http";
import type { PackageItem, RequirementRow, SessionInfo } from "../../api/types";
import { AddLibraryDialog } from "./AddLibraryDialog";
import { JobProgress, type JobLabels } from "./JobProgress";
import { rowErrors, usePackages } from "./usePackages";
import dlg from "../../styles/dialog.module.css";
import styles from "./Spark.module.css";

interface Props {
  version: string;
  envDir: string | null;
  /** Sessões abertas do kernel deste ambiente (bloqueiam as ações). */
  sessions: SessionInfo[];
  onClose: () => void;
}

const JOB_LABELS: JobLabels = {
  running: "Applying changes…",
  succeeded: "Changes applied",
  failed: "Changes failed",
  log: "Libraries job log",
};

function actionError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409)
    return `Blocked: close the notebooks that use this environment and wait for other jobs to finish. (${err.message})`;
  if (err instanceof ApiError && err.status === 404) return "This version is no longer installed.";
  return errorMessage(err);
}

function Row({ item, selected, changed, added, disabled, onToggle }: { item: PackageItem; selected: boolean; changed: boolean; added: boolean; disabled: boolean; onToggle: () => void }) {
  return (
    <tr className={`${selected ? styles.pkgSelected : ""} ${changed ? styles.pkgChanged : ""}`} data-testid="spark-package-row" data-name={item.name}>
      <td className={styles.pkgCheck}>
        <input type="checkbox" checked={selected} disabled={disabled} aria-label={`Select ${item.name}`} onChange={onToggle} />
      </td>
      <td className={styles.pkgName}>
        <span>{item.name}</span>
        {added ? <span className={`${styles.tag} ${styles.tagNew}`}>new</span> : null}
      </td>
      <td>{item.version}</td>
    </tr>
  );
}

export function PackagesDialog({ version, envDir, sessions, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const pk = usePackages(version);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);
  const busy = pk.job !== null && pk.job.status === "running";
  const locked = busy || pk.pending;

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  // A lista muda após cada job: descarta marcas de libs que sumiram.
  useEffect(() => {
    const names = new Set(pk.packages.map((p) => p.name));
    setSelected((s) => (Array.from(s).every((n) => names.has(n)) ? s : new Set(Array.from(s).filter((n) => names.has(n)))));
  }, [pk.packages]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? pk.packages.filter((p) => p.name.toLowerCase().includes(q)) : pk.packages;
  }, [pk.packages, filter]);

  const chosen = pk.packages.filter((p) => selected.has(p.name));
  const sessionReason =
    sessions.length > 0
      ? `In use by ${sessions.length === 1 ? "1 open notebook" : `${sessions.length} open notebooks`}. Close the tab to change libraries.`
      : null;
  const blockReason = locked ? "A job is running." : sessionReason;
  const needsSelection = chosen.length === 0 ? "Select libraries first." : null;

  const toggle = (name: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const run = async (start: () => Promise<void>) => {
    setActionErr(null);
    setShowLog(false);
    try {
      await start();
      setSelected(new Set());
    } catch (err) {
      // 422 por linha é mostrado no próprio AddLibraryDialog.
      if (!rowErrors(err)) setActionErr(actionError(err));
      throw err;
    }
  };

  const uninstall = () => {
    void run(() => pk.uninstall(chosen.map((p) => p.name))).catch(() => undefined);
  };
  const upgrade = () => {
    void run(() => pk.upgrade(chosen.map((p) => p.name))).catch(() => undefined);
  };
  const add = (rows: RequirementRow[]) => run(() => pk.add(rows));

  const close = () => {
    if (!locked) ref.current?.close();
  };

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.pkgDialog}`}
      aria-labelledby="pkg-title"
      data-testid="spark-packages-dialog"
      onCancel={(e) => {
        // O <dialog> aninhado de AddLibraryDialog propaga cancel/close por aqui.
        if (e.target !== e.currentTarget) return;
        if (locked) e.preventDefault();
      }}
      onClose={(e) => {
        if (e.target !== e.currentTarget) return;
        const d = ref.current;
        if (locked && d && !d.open) d.showModal();
        else onClose();
      }}
      onClick={(e) => e.target === e.currentTarget && close()}
    >
      <div className={dlg.head}>
        <div>
          <h2 id="pkg-title" className={dlg.title}>
            Spark {version} — Libraries
          </h2>
          <p className={styles.text}>
            {envDir ? <span>{envDir}</span> : null} · PyPI only
          </p>
        </div>
        <button type="button" className="btn btn-ghost" aria-label="Close dialog" disabled={locked} onClick={close}>
          ✕
        </button>
      </div>

      <div className={styles.pkgToolbar}>
        <span title={blockReason ?? "Add libraries"}>
          <button type="button" className="btn btn-primary" aria-label="Add libraries" disabled={!!blockReason || pk.loading} onClick={() => setAddOpen(true)}>
            ＋
          </button>
        </span>
        <span title={blockReason ?? needsSelection ?? "Uninstall selected"}>
          <button type="button" className={`btn ${styles.dangerBtn}`} aria-label="Uninstall selected" disabled={!!blockReason || !!needsSelection} onClick={uninstall}>
            −
          </button>
        </span>
        <span title={blockReason ?? needsSelection ?? "Upgrade selected to the latest version"}>
          <button type="button" className="btn" aria-label="Upgrade selected" disabled={!!blockReason || !!needsSelection} onClick={upgrade}>
            ↑
          </button>
        </span>
        <input
          className={`${styles.input} ${styles.pkgFilter}`}
          type="search"
          placeholder="Filter libraries…"
          aria-label="Filter libraries"
          value={filter}
          disabled={locked}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {sessionReason && !locked ? <p className={styles.notice}>{sessionReason}</p> : null}
      {chosen.length > 0 ? (
        <p className={styles.pkgSummary} data-testid="spark-packages-selected">
          {chosen.length} selected: {chosen.map((p) => `${p.name} ${p.version}`).join(", ")} — − uninstalls · ↑ upgrades to latest
        </p>
      ) : null}
      {actionErr ? <p className={styles.error}>{actionErr}</p> : null}

      {pk.job ? (
        <div className={styles.pkgJob}>
          <JobProgress job={pk.job} title="Libraries" labels={JOB_LABELS} indeterminate />
          {pk.job.status === "lost" ? <p className={styles.error}>{pk.job.message}</p> : null}
        </div>
      ) : null}
      {pk.result ? (
        <div className={`${styles.banner} ${pk.result.ok ? styles.bannerOk : styles.bannerBad}`} data-testid="spark-packages-result" role="status">
          <span className={styles.bannerText}>
            {pk.result.ok ? "✓ " : "✕ "}
            {pk.result.text}
          </span>
          <button type="button" className="btn btn-ghost" onClick={() => setShowLog((v) => !v)}>
            {showLog ? "Hide log" : "View log"}
          </button>
          <button type="button" className="btn btn-ghost" aria-label="Dismiss result" onClick={pk.dismissResult}>
            ✕
          </button>
        </div>
      ) : null}
      {pk.result && showLog ? (
        <div className={styles.log} tabIndex={0} aria-label="Job log">
          {pk.result.job.lines.map((l, i) => (
            <div key={i} className={styles.logText}>
              {l.line}
            </div>
          ))}
        </div>
      ) : null}

      <div className={styles.pkgScroll}>
        {pk.loading ? <p className={styles.text}>Loading…</p> : null}
        {pk.error ? <p className={styles.error}>Could not list the libraries: {pk.error}</p> : null}
        {!pk.loading && !pk.error ? (
          <table className={styles.pkgTable}>
            <thead>
              <tr>
                <th />
                <th>Library</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((p) => (
                <Row key={p.name} item={p} selected={selected.has(p.name)} changed={pk.changed.has(p.name)} added={pk.added.has(p.name)} disabled={locked} onToggle={() => toggle(p.name)} />
              ))}
            </tbody>
          </table>
        ) : null}
        {!pk.loading && !pk.error && visible.length === 0 ? <p className={styles.text}>No libraries match.</p> : null}
      </div>

      <div className={dlg.foot}>
        <span className={styles.footNote}>
          {pk.packages.length} libraries
        </span>
        <button type="button" className="btn" disabled={locked} onClick={close}>
          Close
        </button>
      </div>

      {addOpen ? <AddLibraryDialog onSubmit={add} onClose={() => setAddOpen(false)} /> : null}
    </dialog>
  );
}
