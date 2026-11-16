/** Cartão Connections do Explorer: raiz Notislake e, se habilitada, a pasta local salva como conexão. Sem cabeçalho: não recolhe. */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useStore } from "zustand";
import { basename } from "../../lib/paths";
import { getNotislakeLocalCredentials } from "../../api/notislake";
import { useFiles } from "../../state/files";
import { isNotislakeTreeAvailable, useNotislake } from "../../state/notislake";
import { activeNotebookPath, useRouter } from "../../state/router";
import { getEntry, useWorkspace, type NotebookEntry } from "../../state/workspace";
import { ContextMenu } from "../shell/ContextMenu";
import type { MenuItem } from "../shell/Menu";
import { BucketIcon, FolderIcon } from "../shell/icons";
import { FileTree } from "./FileTree";
import { NotislakeConnectionDialog } from "./NotislakeConnectionDialog";
import { NotislakeTree } from "./NotislakeTree";
import styles from "./DataPanel.module.css";

const COPY_FEEDBACK_MS = 2000;
const REFRESH_DEBOUNCE_MS = 1500;

/** Interruptor único: false esconde a raiz de pasta local; a pasta salva em useFiles fica preservada. */
const LOCAL_FOLDERS_ENABLED = false;

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
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
  const path = useRouter((s) => activeNotebookPath(s.route));
  useWorkspace((s) => s.tabs);
  const entry = path ? getEntry(path) : undefined;

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
  const consoleUrl = local?.console_url ?? null;

  const running = !manual && local?.state === "running";

  function openMenu() {
    const r = triggerRef.current?.getBoundingClientRect();
    if (r) setMenu({ x: r.left, y: r.bottom });
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
      label: "Copiar credenciais",
      disabled: !running,
      onSelect: () => void copyCredentials(),
      testId: "notislake-copy-credentials",
    },
    "separator",
    { label: "Settings", onSelect: onConfigure, testId: "notislake-settings" },
  ];

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
    body = <p className={styles.notice}>Invalid connection settings. Use Notislake → Settings.</p>;
  } else if (statusError && !status) {
    body = <p className={styles.notice}>{statusError}</p>;
  } else {
    body = <p className={styles.hint}>{status ? "MinIO is not running." : "Checking MinIO…"}</p>;
  }

  return (
    <div className={styles.notislakeRoot} data-testid="notislake-root">
      <div className={styles.connection} title="Notislake (MinIO / S3)">
        <BucketIcon size={14} />
        <button
          ref={triggerRef}
          type="button"
          className={`${styles.connectionName} ${styles.notislakeTrigger}`}
          aria-haspopup="menu"
          aria-expanded={menu !== null}
          onClick={openMenu}
        >
          Notislake
        </button>
      </div>
      <div className={styles.notislakeBody}>{body}</div>
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems}
          ariaLabel="Notislake actions"
          onClose={closeMenu}
          returnFocusTo={triggerRef.current}
        />
      ) : null}
      <div className={`${styles.copyFeedback} ${copied === "error" ? styles.treeError : ""}`} role="status" aria-live="polite">
        {copied === "ok" ? "Credenciais copiadas" : copied === "error" ? "Não foi possível copiar as credenciais" : null}
      </div>
    </div>
  );
}

export function FilesSection(_props: { collapsed: boolean; onToggle: () => void; onExpand: () => void }) {
  const root = useFiles((s) => s.root);
  const [configuring, setConfiguring] = useState(false);

  return (
    <section className={`${styles.section} ${styles.sectionHeaderless}`} data-testid="data-files" aria-label="Connections">
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
      <NotislakeRoot onConfigure={() => setConfiguring(true)} />
      <NotislakeConnectionDialog open={configuring} onClose={() => setConfiguring(false)} />
    </section>
  );
}
