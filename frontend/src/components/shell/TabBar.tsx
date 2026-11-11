/** Abas dos notebooks abertos: ativa = rota; × fecha (encerra a sessão do kernel). */
import { useStore } from "zustand";
import { notebookTitle } from "../../lib/paths";
import { activeNotebookPath, openNotebook, useRouter } from "../../state/router";
import { getEntry, type NotebookEntry, useWorkspace } from "../../state/workspace";
import styles from "./AppShell.module.css";
import { CloseIcon, FolderIcon, NotebookIcon } from "./icons";

function Tab({ path, active }: { path: string; active: boolean }) {
  const entry = getEntry(path);
  if (!entry) return null;
  return <TabInner path={path} active={active} entry={entry} />;
}

function TabInner({ path, active, entry }: { path: string; active: boolean; entry: NotebookEntry }) {
  const dirty = useStore(entry.notebook, (s) => s.dirty);
  const closeTab = useWorkspace((s) => s.closeTab);
  return (
    <div className={styles.tab} data-active={active || undefined} data-testid="notebook-tab" data-path={path} title={path}>
      <button
        type="button"
        role="tab"
        aria-selected={active}
        className={styles.tabMain}
        onClick={() => openNotebook(path)}
        onAuxClick={(e) => e.button === 1 && closeTab(path)}
      >
        <NotebookIcon size={13} />
        <span className={styles.tabLabel}>{notebookTitle(path)}</span>
        {dirty ? <span className={styles.tabDirty} aria-label="Unsaved changes" title="Unsaved changes" data-testid="tab-dirty" /> : null}
      </button>
      <button
        type="button"
        className={styles.tabClose}
        aria-label={`Close ${notebookTitle(path)}`}
        title="Close"
        data-testid="notebook-tab-close"
        onClick={() => closeTab(path)}
      >
        <CloseIcon size={11} />
      </button>
    </div>
  );
}

export function TabBar() {
  const tabs = useWorkspace((s) => s.tabs);
  const active = useRouter((s) => activeNotebookPath(s.route));
  const explorerOpen = useWorkspace((s) => s.explorerOpen);
  const setExplorerOpen = useWorkspace((s) => s.setExplorerOpen);
  if (tabs.length === 0) return null;
  return (
    <div className={styles.tabBar}>
      {explorerOpen ? null : (
        <button
          type="button"
          className={`${styles.iconBtn} ${styles.tabsReopen}`}
          aria-label="Show Explorer (⌘B)"
          title="Show Explorer (⌘B)"
          data-testid="explorer-reopen"
          onClick={() => setExplorerOpen(true)}
        >
          <FolderIcon size={14} />
        </button>
      )}
      <div className={styles.tabs} role="tablist" aria-label="Open notebooks">
        {tabs.map((p) => (
          <Tab key={p} path={p} active={p === active} />
        ))}
      </div>
    </div>
  );
}
