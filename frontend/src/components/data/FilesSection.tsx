/** Cartão Connections do Explorer: a pasta local escolhida como conexão (ícone + nome, caminho no tooltip) e sua árvore; corpo desmontado quando recolhido. */
import { useState } from "react";
import { basename } from "../../lib/paths";
import { chooseDirectory } from "../../api/files";
import { ApiError, errorMessage } from "../../api/http";
import { useFiles } from "../../state/files";
import { FolderIcon, PlusIcon, RefreshIcon } from "../shell/icons";
import { CardTitle } from "./CardTitle";
import { DirectoryPicker } from "./DirectoryPicker";
import { FileTree } from "./FileTree";
import styles from "./DataPanel.module.css";

export function FilesSection({ collapsed, onToggle, onExpand }: { collapsed: boolean; onToggle: () => void; onExpand: () => void }) {
  const root = useFiles((s) => s.root);
  const setRoot = useFiles((s) => s.setRoot);
  const refresh = useFiles((s) => s.refresh);
  const [opening, setOpening] = useState(false);
  const [manual, setManual] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

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
          {root ? (
            <button type="button" className="btn btn-ghost" onClick={refresh} aria-label="Refresh tree" title="Refresh">
              <RefreshIcon size={14} />
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost"
            data-testid="files-select-dir"
            disabled={opening}
            onClick={() => void choose()}
            aria-label={root ? "Change folder" : "Add local folder"}
            title={opening ? "Opening Finder…" : root ? "Change folder" : "Add local folder"}
          >
            <PlusIcon size={14} />
          </button>
        </div>
      </div>
      {collapsed ? null : (
        <>
        {notice ? (
          <p className={styles.notice} role="alert">
            {notice}
          </p>
        ) : null}
        {manual ? (
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
        {root ? (
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
        </>
      )}
    </section>
  );
}
