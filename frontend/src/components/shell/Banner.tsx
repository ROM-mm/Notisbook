/**
 * Barra superior única do shell: marca N + "notisbook",
 * menus File/Edit/View/Run/Help revelados no hover da barra inteira (ou com foco/menu
 * aberto), nomes dos notebooks abertos lado a lado (ativo = rota; dirty, ×, clique do
 * meio e "+") e, à direita, uso da máquina, estado de salvamento, controles do kernel
 * da aba ativa ("● nome.ipynb", seletor, ▶, ■, ↻, ⋮) e os toggles das laterais
 * esquerda (⌘B) e direita (⌥⌘B) e do modo foco (⌘.).
 */
import { useStore } from "zustand";
import { notebookTitle } from "../../lib/paths";
import { NotebookProvider, useNotebook } from "../../state/notebookContext";
import { activeNotebookPath, openNotebook, useRouter } from "../../state/router";
import { getEntry, type NotebookEntry, useWorkspace } from "../../state/workspace";
import { KernelToolbar } from "../kernel/KernelToolbar";
import styles from "./Banner.module.css";
import { BrandMark, CloseIcon, FocusIcon, PanelLeftIcon, PanelRightIcon, PlusIcon } from "./icons";
import { MenuBar, newNotebook } from "./MenuBar";
import { SystemResources } from "./SystemResources";

function SaveState() {
  const saving = useNotebook((s) => s.saving);
  const saveError = useNotebook((s) => s.saveError);
  const dirty = useNotebook((s) => s.dirty);
  const ready = useNotebook((s) => s.status === "ready");
  if (!ready) return null;
  if (!saving && !saveError && dirty) return null;
  const text = saving ? "Saving…" : saveError ? "Save failed" : "Saved";
  return (
    <span className={saveError ? `${styles.saveText} ${styles.saveError}` : styles.saveText} title={saveError ?? undefined} data-testid="save-state">
      {text}
    </span>
  );
}

function PanelToggle({ side }: { side: "left" | "right" }) {
  const open = useWorkspace((s) => (side === "left" ? s.leftOpen : s.rightOpen) && !s.focusMode);
  const toggle = useWorkspace((s) => (side === "left" ? s.toggleLeft : s.toggleRight));
  const left = side === "left";
  return (
    <button
      type="button"
      className={styles.toggle}
      data-testid={`toggle-${side}-panel`}
      title={left ? "Left panel (⌘B)" : "Right panel (⌥⌘B)"}
      aria-label={left ? "Left panel" : "Right panel"}
      aria-pressed={open}
      onClick={toggle}
    >
      {left ? <PanelLeftIcon size={15} /> : <PanelRightIcon size={15} />}
    </button>
  );
}

function FocusToggle() {
  const on = useWorkspace((s) => s.focusMode);
  const toggle = useWorkspace((s) => s.toggleFocusMode);
  return (
    <button
      type="button"
      className={styles.toggle}
      data-testid="toggle-focus"
      title="Focus mode (⌘.)"
      aria-label="Focus mode"
      aria-pressed={on}
      onClick={toggle}
    >
      <FocusIcon size={15} />
    </button>
  );
}

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
        <CloseIcon size={10} />
      </button>
    </div>
  );
}

/** Nomes dos notebooks abertos na barra superior; o "+" cria um notebook. */
function NotebookTabs({ entry }: { entry: NotebookEntry | null }) {
  const tabs = useWorkspace((s) => s.tabs);
  const active = useRouter((s) => activeNotebookPath(s.route));
  if (tabs.length === 0) return null;
  return (
    <div className={styles.tabBar}>
      <div className={styles.tabs} role="tablist" aria-label="Open notebooks">
        {tabs.map((p) => (
          <Tab key={p} path={p} active={p === active} />
        ))}
      </div>
      <button
        type="button"
        className={styles.tabAdd}
        aria-label="New notebook"
        title="New notebook"
        data-testid="tab-new"
        onClick={() => newNotebook(entry)}
      >
        <PlusIcon size={13} />
      </button>
    </div>
  );
}

export function Banner({ entry }: { entry: NotebookEntry | null }) {
  return (
    <header className={styles.banner} aria-label="Notisbook">
      <div className={styles.brand}>
        <BrandMark size={18} />
        <span className={styles.wordmark}>notisbook</span>
      </div>
      <MenuBar entry={entry} />
      <NotebookTabs entry={entry} />
      <div className={styles.actions}>
        {entry ? (
          <NotebookProvider entry={entry}>
            <SystemResources />
            <SaveState />
            <KernelToolbar />
          </NotebookProvider>
        ) : null}
        <span className={styles.toggles}>
          <PanelToggle side="left" />
          <PanelToggle side="right" />
          <FocusToggle />
        </span>
      </div>
    </header>
  );
}
