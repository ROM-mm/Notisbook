/**
 * Cartão Notislake do Explorer: cabeçalho com o título recolhível e os botões Refresh e "+"
 * (Create bucket, só no MinIO local); botão direito no cabeçalho abre o menu da conexão
 * (MinIO UI, Copy credentials, Settings). Abaixo, um nó `s3://<bucket>` por bucket; se
 * habilitada, a pasta local salva como conexão.
 */
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { useStore } from "zustand";
import { basename } from "../../lib/paths";
import { getNotislakeLocalCredentials } from "../../api/notislake";
import { LOCAL_FOLDERS_ENABLED, useFiles } from "../../state/files";
import { isNotislakeManageable, isNotislakeTreeAvailable, useNotislake } from "../../state/notislake";
import { activeNotebookPath, useRouter } from "../../state/router";
import { getEntry, useWorkspace, type NotebookEntry } from "../../state/workspace";
import { ContextMenu } from "../shell/ContextMenu";
import type { MenuItem } from "../shell/Menu";
import { FolderIcon, PlusIcon, RefreshIcon } from "../shell/icons";
import { CardTitle } from "./CardTitle";
import { CreateBucketDialog } from "./CreateBucketDialog";
import { FileTree } from "./FileTree";
import { NotislakeConnectionDialog } from "./NotislakeConnectionDialog";
import { NotislakeTree } from "./NotislakeTree";
import styles from "./DataPanel.module.css";

const COPY_FEEDBACK_MS = 2000;
const REFRESH_DEBOUNCE_MS = 1500;

/** Relê a árvore na transição busy → idle do kernel do notebook ativo (célula pode ter criado ou excluído tabelas). */
function IdleRefresh({ entry }: { entry: NotebookEntry }) {
  const kernelState = useStore(entry.kernel, (s) => s.kernelState);
  const previous = useRef(kernelState);
  useEffect(() => {
    const was = previous.current;
    previous.current = kernelState;
    if (kernelState !== "idle" || was !== "busy") return;
    const timer = setTimeout(() => {
      if (!document.hidden) useNotislake.getState().refreshExpanded();
    }, REFRESH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [kernelState]);
  return null;
}

/** Corpo do Notislake: a árvore só aparece em `running`/manual; os demais estados mostram diagnóstico e ações. */
function NotislakeRoot() {
  const status = useNotislake((s) => s.status);
  const statusError = useNotislake((s) => s.statusError);
  const retrying = useNotislake((s) => s.retrying);
  const retryError = useNotislake((s) => s.retryError);
  const retry = useNotislake((s) => s.retry);
  const path = useRouter((s) => activeNotebookPath(s.route));
  useWorkspace((s) => s.tabs);
  const entry = path ? getEntry(path) : undefined;

  const local = status?.local ?? null;
  const manual = status?.mode === "manual";
  const available = isNotislakeTreeAvailable(status);

  let body: ReactNode;
  if (available) {
    body = (
      <>
        {entry ? <IdleRefresh key={entry.path} entry={entry} /> : null}
        <NotislakeTree />
      </>
    );
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
    body = <p className={styles.notice}>Invalid connection settings. Right-click NOTISLAKE → Settings.</p>;
  } else if (statusError && !status) {
    body = <p className={styles.notice}>{statusError}</p>;
  } else {
    body = <p className={styles.hint}>{status ? "MinIO is not running." : "Checking MinIO…"}</p>;
  }

  return (
    <div className={styles.notislakeRoot} data-testid="notislake-root">
      {body}
    </div>
  );
}

/** Recolher só esconde o corpo: o cartão continua montado (polling do status e IdleRefresh). */
export function FilesSection({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const root = useFiles((s) => s.root);
  const status = useNotislake((s) => s.status);
  const start = useNotislake((s) => s.start);
  const stop = useNotislake((s) => s.stop);
  const refresh = useNotislake((s) => s.refresh);
  const [configuring, setConfiguring] = useState(false);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<"ok" | "error" | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  useEffect(() => {
    if (copied === null) return;
    const id = setTimeout(() => setCopied(null), COPY_FEEDBACK_MS);
    return () => clearTimeout(id);
  }, [copied]);

  const manual = status?.mode === "manual";
  const running = !manual && status?.local?.state === "running";
  const consoleUrl = status?.local?.console_url ?? null;
  const manageable = isNotislakeManageable(status);

  // Menu da conexão: botão direito no cabeçalho; pelo teclado, tecla ContextMenu ou Shift+F10 no título.
  function onHeaderContextMenu(e: MouseEvent<HTMLDivElement>) {
    e.preventDefault();
    if (e.clientX === 0 && e.clientY === 0) openMenuAtHeader();
    else setMenu({ x: e.clientX, y: e.clientY });
  }

  function openMenuAtHeader() {
    const r = headerRef.current?.getBoundingClientRect();
    if (r) setMenu({ x: r.left + 12, y: r.bottom });
  }

  function onHeaderKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) {
      e.preventDefault();
      openMenuAtHeader();
    }
  }

  // A credencial vive só neste handler; a Promise no ClipboardItem preserva o gesto do clique (Safari).
  async function copyCredentials() {
    const toText = ({ user, password }: { user: string; password: string }) => `${user}\n${password}`;
    try {
      if (typeof ClipboardItem !== "undefined" && navigator.clipboard.write) {
        const blob = getNotislakeLocalCredentials().then((c) => new Blob([toText(c)], { type: "text/plain" }));
        await navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })]);
      } else {
        await navigator.clipboard.writeText(toText(await getNotislakeLocalCredentials()));
      }
      setCopied("ok");
    } catch {
      setCopied("error");
    }
  }

  const menuItems: MenuItem[] = [
    {
      label: "MinIO UI",
      disabled: !running || !consoleUrl,
      onSelect: () => {
        if (consoleUrl) window.open(consoleUrl, "_blank", "noopener,noreferrer");
      },
      testId: "notislake-open-minio-ui",
    },
    {
      label: "Copy credentials",
      disabled: !running,
      onSelect: () => void copyCredentials(),
      testId: "notislake-copy-credentials",
    },
    "separator",
    { label: "Settings", onSelect: () => setConfiguring(true), testId: "notislake-settings" },
  ];

  return (
    <section
      className={`${styles.section} ${collapsed ? styles.sectionCollapsed : ""}`}
      data-testid="data-files"
      aria-labelledby="notislake-title"
    >
      <div
        ref={headerRef}
        className={styles.sectionHeader}
        data-testid="notislake-header"
        onContextMenu={onHeaderContextMenu}
        onKeyDown={onHeaderKeyDown}
      >
        <CardTitle
          id="notislake-title"
          label="Notislake"
          collapsed={collapsed}
          onToggle={onToggle}
          title="Right-click for MinIO UI, credentials and settings"
        />
        <div className={styles.sectionActions}>
          <button
            type="button"
            className="btn btn-ghost"
            data-testid="notislake-refresh"
            onClick={() => refresh()}
            aria-label="Refresh buckets"
            title="Refresh"
          >
            <RefreshIcon size={14} />
          </button>
          {manual ? null : (
            <button
              type="button"
              className="btn btn-ghost"
              data-testid="notislake-add-bucket"
              disabled={!manageable}
              onClick={() => setCreating(true)}
              aria-label="Create bucket"
              title="Create bucket"
            >
              <PlusIcon size={14} />
            </button>
          )}
        </div>
      </div>
      <div className={styles.notislakeContent} hidden={collapsed}>
        {LOCAL_FOLDERS_ENABLED && root ? (
          <>
            <div className={styles.connection} title={root}>
              <FolderIcon size={14} />
              <span className={styles.connectionName}>{basename(root) || root}</span>
            </div>
            <div className={styles.tree}>
              <FileTree root={root} />
            </div>
          </>
        ) : null}
        <NotislakeRoot />
        <div className={`${styles.copyFeedback} ${copied === "error" ? styles.treeError : ""}`} role="status" aria-live="polite">
          {copied === "ok" ? "Credentials copied" : copied === "error" ? "Could not copy the credentials" : null}
        </div>
      </div>
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems}
          ariaLabel="Notislake actions"
          onClose={closeMenu}
          returnFocusTo={headerRef.current?.querySelector<HTMLElement>("button") ?? null}
        />
      ) : null}
      {creating ? <CreateBucketDialog onClose={() => setCreating(false)} /> : null}
      <NotislakeConnectionDialog open={configuring} onClose={() => setConfiguring(false)} />
    </section>
  );
}
