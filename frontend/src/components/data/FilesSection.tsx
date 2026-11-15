/** Cartão Connections do Explorer: a pasta local escolhida como conexão (ícone + nome, caminho no tooltip) e sua árvore; corpo desmontado quando recolhido. */
import { useEffect, useState, type ReactNode } from "react";
import { basename } from "../../lib/paths";
import { chooseDirectory } from "../../api/files";
import { ApiError, errorMessage } from "../../api/http";
import { useFiles } from "../../state/files";
import { isNotislakeTreeAvailable, useNotislake } from "../../state/notislake";
import { FolderIcon, PlusIcon, RefreshIcon } from "../shell/icons";
import { BrandIcon } from "./BrandIcon";
import { CardTitle } from "./CardTitle";
import { DirectoryPicker } from "./DirectoryPicker";
import { FileTree } from "./FileTree";
import { NotislakeConnectionDialog } from "./NotislakeConnectionDialog";
import { NotislakeTree } from "./NotislakeTree";
import styles from "./DataPanel.module.css";
import s3IconUrl from "../../../icons/s3.png";

const COPY_FEEDBACK_MS = 2000;

/** Interruptor único: false esconde a raiz de pasta local e desabilita o "+". O código e a pasta salva ficam preservados. */
const LOCAL_FOLDERS_ENABLED = false;

/** Raiz fixa do Notislake: a árvore só aparece em `running`/manual; os demais estados mostram diagnóstico e ações. */
function NotislakeRoot({ onConfigure }: { onConfigure: () => void }) {
  const status = useNotislake((s) => s.status);
  const statusError = useNotislake((s) => s.statusError);
  const retrying = useNotislake((s) => s.retrying);
  const retryError = useNotislake((s) => s.retryError);
  const start = useNotislake((s) => s.start);
  const stop = useNotislake((s) => s.stop);
  const retry = useNotislake((s) => s.retry);
  const [copied, setCopied] = useState<"ok" | "error" | null>(null);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  useEffect(() => {
    if (copied === null) return;
    const id = setTimeout(() => setCopied(null), COPY_FEEDBACK_MS);
    return () => clearTimeout(id);
  }, [copied]);

  const local = status?.local ?? null;
  const manual = status?.mode === "manual";
  const available = isNotislakeTreeAvailable(status);
  const credentialsPath = local?.credentials_path ?? null;
  const consoleUrl = local?.console_url ?? null;

  async function copyCredentialsPath() {
    if (!credentialsPath) return;
    try {
      await navigator.clipboard.writeText(credentialsPath);
      setCopied("ok");
    } catch {
      setCopied("error");
    }
  }

  let body: ReactNode;
  if (available) {
    body = <NotislakeTree />;
  } else if (!manual && local?.state === "restarting") {
    body = (
      <p className={styles.hint} role="status">
        Restarting MinIO… attempt {local.restarts}
      </p>
    );
  } else if (!manual && local?.state === "failed") {
    body = (
      <div className={styles.notislakeStatus} role="alert">
        <p className={styles.notice}>{local.error?.message ?? "MinIO failed to start."}</p>
        <button type="button" className="btn btn-ghost" disabled={retrying} onClick={retry}>
          {retrying ? "Retrying…" : "Retry"}
        </button>
        {retryError ? <p className={styles.notice}>{retryError}</p> : null}
      </div>
    );
  } else if (status?.mode === "invalid") {
    body = <p className={styles.notice}>Invalid connection settings. Use Configure connection…</p>;
  } else if (statusError && !status) {
    body = <p className={styles.notice}>{statusError}</p>;
  } else {
    body = <p className={styles.hint}>{status ? "MinIO is not running." : "Checking MinIO…"}</p>;
  }

  return (
    <div className={styles.notislakeRoot} data-testid="notislake-root">
      <div className={styles.connection} title="Notislake (MinIO / S3)">
        <BrandIcon src={s3IconUrl} />
        <span className={styles.connectionName}>notislake (minio)</span>
        <button type="button" className={`btn btn-ghost ${styles.notislakeConfigure}`} onClick={onConfigure}>
          Configure connection…
        </button>
      </div>
      <div className={styles.tree}>{body}</div>
      {consoleUrl || credentialsPath ? (
        <div className={styles.notislakeFooter}>
          {consoleUrl ? (
            <a href={consoleUrl} target="_blank" rel="noopener noreferrer" className={styles.notislakeLink}>
              MinIO console
            </a>
          ) : null}
          {credentialsPath ? (
            <span className={styles.notislakeCreds}>
              <span className={styles.notislakePath} title={credentialsPath}>
                {credentialsPath}
              </span>
              <button type="button" className="btn btn-ghost" onClick={() => void copyCredentialsPath()} aria-label="Copy credentials path" title="Copy credentials path">
                {copied === "ok" ? "Copied" : copied === "error" ? "Copy failed" : "Copy"}
              </button>
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function FilesSection({ collapsed, onToggle, onExpand }: { collapsed: boolean; onToggle: () => void; onExpand: () => void }) {
  const root = useFiles((s) => s.root);
  const setRoot = useFiles((s) => s.setRoot);
  const refresh = useFiles((s) => s.refresh);
  const [opening, setOpening] = useState(false);
  const [manual, setManual] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [configuring, setConfiguring] = useState(false);

  // Feedback só existe no corpo, desmontado quando recolhido: expande antes de exibi-lo.
  function showNotice(message: string) {
    setNotice(message);
    onExpand();
  }

  function openManual() {
    setManual(true);
    onExpand();
  }

  async function choose() {
    onExpand();
    setOpening(true);
    setNotice(null);
    try {
      const res = await chooseDirectory(root);
      if (res.path) setRoot(res.path);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : null;
      if (status === 409) {
        showNotice("A folder picker is already open. Check Finder (it may be behind the browser).");
      } else if (status === 504) {
        showNotice("Timed out choosing the folder.");
      } else if (status === 501) {
        showNotice("Native picker unavailable on this system. Enter the path below.");
        openManual();
      } else {
        showNotice(`${errorMessage(err)} Enter the path below.`);
        openManual();
      }
    } finally {
      setOpening(false);
    }
  }

  return (
    <section className={`${styles.section} ${collapsed ? styles.sectionCollapsed : ""}`} data-testid="data-files" aria-labelledby="data-connections-title">
      <div className={styles.sectionHeader}>
        <CardTitle id="data-connections-title" icon={<FolderIcon size={14} />} label="Connections" collapsed={collapsed} onToggle={onToggle} />
        <div className={styles.sectionActions}>
          {LOCAL_FOLDERS_ENABLED && root ? (
            <button type="button" className="btn btn-ghost" onClick={refresh} aria-label="Refresh tree" title="Refresh">
              <RefreshIcon size={14} />
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost"
            data-testid="files-select-dir"
            disabled={opening || !LOCAL_FOLDERS_ENABLED}
            onClick={() => void choose()}
            aria-label={root ? "Change folder" : "Add local folder"}
            title={
              !LOCAL_FOLDERS_ENABLED
                ? "Local folders are temporarily disabled"
                : opening
                  ? "Opening Finder…"
                  : root
                    ? "Change folder"
                    : "Add local folder"
            }
          >
            <PlusIcon size={14} />
          </button>
        </div>
      </div>
      {collapsed ? null : (
        <>
        {LOCAL_FOLDERS_ENABLED && notice ? (
          <p className={styles.notice} role="alert">
            {notice}
          </p>
        ) : null}
        {LOCAL_FOLDERS_ENABLED && manual ? (
          <DirectoryPicker
            initialPath={root}
            onCancel={() => {
              setManual(false);
              setNotice(null);
            }}
            onSelect={(p) => {
              setRoot(p);
              setManual(false);
              setNotice(null);
            }}
          />
        ) : null}
        {!LOCAL_FOLDERS_ENABLED ? null : root ? (
          <>
            <div className={styles.connection} title={root}>
              <FolderIcon size={14} />
              <span className={styles.connectionName}>{basename(root) || root}</span>
            </div>
            <div className={styles.tree}>
              <FileTree root={root} />
            </div>
          </>
        ) : (
          <div className={styles.tree}>
            <p className={styles.hint}>No connection yet. Use + to add a local folder.</p>
          </div>
        )}
        <NotislakeRoot onConfigure={() => setConfiguring(true)} />
        </>
      )}
      <NotislakeConnectionDialog open={configuring} onClose={() => setConfiguring(false)} />
    </section>
  );
}
