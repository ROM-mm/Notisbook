/**
 * Cartão Notebooks do Explorer: título recolhível (corpo desmontado) e a árvore expansível
 * (`NotebookTree`, estado em `state/notebookTree`). Cria pasta na pasta alvo (`targetDir`), troca a pasta raiz (`+`);
 * renomear (inline) e excluir ficam no menu de contexto de qualquer nível.
 * Clicar num notebook abre/foca a aba (`/notebooks/<path>`). Trocar a raiz fecha todas as abas antes.
 * Renomear um notebook aberto em aba é bloqueado (a aba e a sessão do kernel
 * apontam para o caminho antigo) — feche a aba antes; excluir segue a mesma regra.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, type ContentEntry, createEntry, deleteEntry, errorMessage, renameEntry } from "../../api";
import { chooseDirectory } from "../../api/files";
import { putNotebooksRoot, validateNotebooksRoot } from "../../api/notebooksRoot";
import { dirname, joinPath, NOTEBOOK_EXT } from "../../lib/paths";
import { useLayout } from "../../state/layout";
import { selectTargetDir, useNotebookTree } from "../../state/notebookTree";
import { useRecent } from "../../state/recent";
import { closeAllTabs, isOpenUnder, reloadSamples, useWorkspace } from "../../state/workspace";
import { FolderIcon, PlusIcon, RefreshIcon } from "../shell/icons";
import { CardTitle } from "../data/CardTitle";
import { DirectoryPicker } from "../data/DirectoryPicker";
import cardStyles from "../data/DataPanel.module.css";
import styles from "./FileBrowser.module.css";
import { type Draft, NotebookTree } from "./NotebookTree";

const SESSIONS_RETRIES = 6;
const SESSIONS_RETRY_MS = 500;
/** Espera após o último `resize` da janela antes de remedir a largura do painel. */
const RESIZE_DEBOUNCE_MS = 150;

function withNotebookExt(name: string): string {
  return name.toLowerCase().endsWith(NOTEBOOK_EXT) ? name : `${name}${NOTEBOOK_EXT}`;
}

export function FileBrowser({ collapsed, onToggle, onExpand }: { collapsed: boolean; onToggle: () => void; onExpand: () => void }) {
  const root = useWorkspace((s) => s.root);
  const applyRoot = useWorkspace((s) => s.applyRoot);
  const rootStatus = useNotebookTree((s) => s.dirs[""]?.status);
  const rootError = useNotebookTree((s) => s.dirs[""]?.error);
  const targetDir = useNotebookTree(selectTargetDir);
  const hasSelection = useNotebookTree((s) => s.selected !== null);
  const [draft, setDraft] = useState<Draft>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [manual, setManual] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const widthManual = useLayout((s) => s.rightPanelWidthManual);

  // Ajusta o painel à largura do conteúdo (encolhe e alarga) enquanto não houver arraste manual.
  // Necessário = maior entre o cabeçalho (título + ícones no gap de design) e a linha do nome mais longo
  // (texto sem truncar, medido por Range), mais a folga fixa à direita de cada um. Recolhido não há linhas.
  const fitToContent = useCallback(() => {
    const layout = useLayout.getState();
    const section = sectionRef.current;
    const panel = section?.closest<HTMLElement>('[data-testid^="side-panel-"]');
    if (layout.rightPanelWidthManual || !section || !panel) return;
    const panelRect = panel.getBoundingClientRect();
    let needed = 0;
    // `contentRight`: borda direita do conteúdo intrínseco de `box`; a folga até a borda do painel não depende da largura.
    const consider = (box: Element, contentRight: number) => {
      needed = Math.max(needed, contentRight - panelRect.left + (panelRect.right - box.getBoundingClientRect().right));
    };
    const header = headerRef.current;
    if (header) {
      const cs = getComputedStyle(header);
      const kids = Array.from(header.children);
      const gaps = (parseFloat(cs.columnGap) || 0) * Math.max(0, kids.length - 1);
      const kidsWidth = kids.reduce((sum, k) => sum + k.getBoundingClientRect().width, 0);
      consider(header, header.getBoundingClientRect().left + parseFloat(cs.paddingLeft) + kidsWidth + gaps + parseFloat(cs.paddingRight));
    }
    const range = document.createRange();
    section.querySelectorAll<HTMLElement>(`.${styles.row}`).forEach((row) => {
      const name = row.querySelector<HTMLElement>(`.${styles.treeName}`);
      if (!name) return;
      range.selectNodeContents(name);
      consider(row, name.getBoundingClientRect().left + range.getBoundingClientRect().width + parseFloat(getComputedStyle(row).paddingRight));
    });
    if (needed > 0) layout.fitRightPanelWidth(needed);
  }, []);
  // `collapsed` troca as linhas medidas; `widthManual` remede quando o duplo clique zera a flag.
  useLayoutEffect(() => {
    fitToContent();
  }, [collapsed, widthManual, fitToContent]);
  // Remede uma vez após a Roboto carregar: antes dela o texto sai medido com a fonte reserva.
  useEffect(() => {
    let active = true;
    void document.fonts.ready.then(() => {
      if (active) fitToContent();
    });
    return () => {
      active = false;
    };
  }, [fitToContent]);
  // O teto (metade da janela) só vale no momento da medição: remede ao redimensionar a janela, com debounce.
  // Largura manual segue intocada (`fitToContent` sai cedo com `rightPanelWidthManual`).
  useEffect(() => {
    let timer: number | undefined;
    const onResize = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(fitToContent, RESIZE_DEBOUNCE_MS);
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.clearTimeout(timer);
    };
  }, [fitToContent]);

  useEffect(() => {
    useNotebookTree.getState().ensureRoot();
  }, []);

  // Com a seleção ativa e sem edição inline, o Esc a limpa, mas só com o foco na árvore
  // (Esc de menu/diálogo fora dela não pode apagar a pasta-alvo).
  useEffect(() => {
    if (!hasSelection || draft !== null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (e.target instanceof Element && e.target.closest('[role="tree"]')) useNotebookTree.getState().select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hasSelection, draft]);

  // Feedback só existe no corpo, desmontado quando recolhido: expande antes de exibi-lo.
  function showNotice(message: string) {
    setNotice(message);
    onExpand();
  }

  function openManual() {
    setManual(true);
    onExpand();
  }

  function startCreate() {
    onExpand();
    const tree = useNotebookTree.getState();
    setNotice(null);
    tree.expandTo(targetDir);
    setDraft({ kind: "create", dir: targetDir });
  }

  async function handleCreate(dir: string, name: string) {
    await createEntry(joinPath(dir, name), "directory");
    setDraft(null);
    await useNotebookTree.getState().reload(dir);
    showNotice(`Folder “${name}” created.`);
  }

  /** PUT da raiz; após fechar abas, o DELETE das sessões pode ainda estar em voo → repete em `sessions_active`. */
  async function putRoot(path: string, retries: number) {
    for (let attempt = 0; ; attempt++) {
      try {
        return await putNotebooksRoot(path);
      } catch (err) {
        const busy = err instanceof ApiError && err.detail === "sessions_active";
        if (!busy || attempt >= retries) throw err;
        await new Promise((resolve) => setTimeout(resolve, SESSIONS_RETRY_MS));
      }
    }
  }

  async function changeRoot(path: string) {
    // Valida antes de fechar abas: uma pasta recusada não custa o trabalho aberto.
    try {
      await validateNotebooksRoot(path);
    } catch (err) {
      showNotice(errorMessage(err));
      return;
    }
    const open = useWorkspace.getState().tabs.length;
    if (open > 0) {
      if (!window.confirm(`Changing the notebooks folder closes ${open === 1 ? "the open notebook" : `all ${open} open notebooks`}. Continue?`)) return;
      if (!closeAllTabs()) return;
    }
    try {
      const next = await putRoot(path, open > 0 ? SESSIONS_RETRIES : 0);
      setManual(false);
      applyRoot(next);
      setDraft(null);
      const tree = useNotebookTree.getState();
      tree.reset();
      showNotice(`Notebooks folder set to “${next.name}”.`);
      await tree.reload("");
    } catch (err) {
      showNotice(errorMessage(err));
    }
  }

  async function chooseRoot() {
    onExpand();
    setSwitching(true);
    setNotice(null);
    try {
      const res = await chooseDirectory(root?.path, undefined, "notebooks");
      if (res.path) await changeRoot(res.path);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : null;
      if (status === 409) showNotice("A folder picker is already open. Check Finder (it may be behind the browser).");
      else if (status === 504) showNotice("Timed out choosing the folder.");
      else {
        showNotice(status === 501 ? "Native picker unavailable on this system. Enter the path below." : `${errorMessage(err)} Enter the path below.`);
        openManual();
      }
    } finally {
      setSwitching(false);
    }
  }

  async function handleRename(entry: ContentEntry, rawName: string) {
    const name = entry.type === "notebook" ? withNotebookExt(rawName) : rawName;
    const parent = dirname(entry.path);
    const target = joinPath(parent, name);
    await renameEntry(entry.path, target);
    useRecent.getState().rename(entry.path, target);
    reloadSamples();
    const tree = useNotebookTree.getState();
    tree.forget(entry.path);
    setDraft(null);
    showNotice(`“${entry.name}” renamed to “${name}”.`);
    await tree.reload(parent);
    tree.select({ path: target, type: entry.type });
  }

  function startRename(entry: ContentEntry) {
    if (isOpenUnder(entry.path)) {
      showNotice(`Close the tab for “${entry.name}” (or for notebooks inside it) before renaming.`);
      return;
    }
    setDraft({ kind: "rename", path: entry.path });
  }

  async function handleDelete(entry: ContentEntry) {
    if (isOpenUnder(entry.path)) {
      showNotice(`Close the tab for “${entry.name}” (or for notebooks inside it) before deleting.`);
      return;
    }
    const suffix = entry.type === "dir" ? " and everything in it" : "";
    if (!window.confirm(`Delete “${entry.name}”${suffix}? This cannot be undone.`)) return;
    const tree = useNotebookTree.getState();
    try {
      await deleteEntry(entry.path);
      useRecent.getState().removeUnder(entry.path);
      reloadSamples();
      tree.forget(entry.path);
      showNotice(`“${entry.name}” deleted.`);
    } catch (err) {
      showNotice(errorMessage(err));
    }
    await tree.reload(dirname(entry.path));
  }

  return (
    <section
      className={`${cardStyles.section} ${collapsed ? cardStyles.sectionCollapsed : ""}`}
      data-testid="file-browser"
      ref={sectionRef}
      aria-labelledby="notebooks-title"
    >
      <div className={cardStyles.sectionHeader} ref={headerRef}>
        <CardTitle
          id="notebooks-title"
          label="Notebooks"
          collapsed={collapsed}
          onToggle={onToggle}
          title={root?.name ?? undefined}
        />
        <div className={cardStyles.sectionActions}>
          <button type="button" className="btn btn-ghost" title="Reload" aria-label="Reload" onClick={() => useNotebookTree.getState().reloadAll()}>
            <RefreshIcon size={14} />
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            title={targetDir ? `New folder in ${targetDir}` : "New folder"}
            aria-label="New folder"
            disabled={rootStatus !== "ready"}
            onClick={startCreate}
          >
            <FolderIcon size={14} />
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            title={root?.locked ? "Notebooks folder fixed by --root" : switching ? "Opening Finder…" : "Change notebooks folder"}
            aria-label="Change notebooks folder"
            data-testid="files-change-root"
            disabled={root === null || root.locked || switching}
            onClick={() => void chooseRoot()}
          >
            <PlusIcon size={14} />
          </button>
        </div>
      </div>

      {collapsed ? null : (
        <>
          {notice ? (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          ) : null}

          {manual ? (
            <DirectoryPicker initialPath={root?.path ?? null} onSelect={(p) => void changeRoot(p)} onCancel={() => setManual(false)} />
          ) : null}

          {rootStatus === "error" ? (
            <div className={styles.error} role="alert">
              <span>Could not list the notebooks folder: {rootError}</span>
              <button type="button" className="btn" onClick={() => void useNotebookTree.getState().reload("")}>
                Try again
              </button>
            </div>
          ) : null}

          <div className={cardStyles.tree}>
            <NotebookTree
              draft={draft}
              onContentChange={fitToContent}
              onCreate={handleCreate}
              onRename={handleRename}
              onCancelDraft={() => setDraft(null)}
              onStartRename={startRename}
              onDelete={(entry) => void handleDelete(entry)}
            />
          </div>
        </>
      )}
    </section>
  );
}
