/** Seção Files do painel Dados: raiz escolhida, PATH absoluto no topo e árvore. */
import { useState } from "react";
import { chooseDirectory } from "../../api/files";
import { ApiError, errorMessage } from "../../api/http";
import { useFiles } from "../../state/files";
import { FolderIcon, PlusIcon, RefreshIcon } from "../shell/icons";
import { DirectoryPicker } from "./DirectoryPicker";
import { FileTree } from "./FileTree";
import styles from "./DataPanel.module.css";

export function FilesSection() {
  const root = useFiles((s) => s.root);
  const setRoot = useFiles((s) => s.setRoot);
  const refresh = useFiles((s) => s.refresh);
  const [opening, setOpening] = useState(false);
  const [manual, setManual] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function choose() {
    setOpening(true);
    setNotice(null);
    try {
      const res = await chooseDirectory(root);
      if (res.path) setRoot(res.path);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : null;
      if (status === 409) {
        setNotice("A folder picker is already open. Check Finder (it may be behind the browser).");
      } else if (status === 504) {
        setNotice("Timed out choosing the folder.");
      } else if (status === 501) {
        setNotice("Native picker unavailable on this system. Enter the path below.");
        setManual(true);
      } else {
        setNotice(`${errorMessage(err)} Enter the path below.`);
        setManual(true);
      }
    } finally {
      setOpening(false);
    }
  }

  return (
    <section className={styles.section} data-testid="data-files" aria-labelledby="data-files-title">
      <div className={styles.sectionHeader}>
        <h3 id="data-files-title" className={styles.sectionTitle}>
          <FolderIcon size={14} /> Files
        </h3>
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
            aria-label={root ? "Change folder" : "Select folder"}
            title={opening ? "Opening Finder…" : root ? "Change folder" : "Select folder"}
          >
            <PlusIcon size={14} />
          </button>
        </div>
      </div>
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
        <div className={styles.tree}>
          <FileTree root={root} />
        </div>
      ) : (
        <div className={styles.tree}>
          <p className={styles.hint}>No directory selected.</p>
        </div>
      )}
    </section>
  );
}
