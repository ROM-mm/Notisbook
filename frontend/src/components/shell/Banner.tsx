/**
 * Header do shell: marca, menubar e, à direita, estado de salvamento e os
 * toggles de Explorer (⌘B), painel direito e modo foco (⌘.). Recebe a aba
 * ativa para os menus e o estado de salvamento.
 */
import { NotebookProvider, useNotebook } from "../../state/notebookContext";
import type { NotebookEntry } from "../../state/workspace";
import { useWorkspace } from "../../state/workspace";
import styles from "./Banner.module.css";
import { BrandMark, FocusIcon, FolderIcon, VariablesIcon } from "./icons";
import { MenuBar } from "./MenuBar";
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

function ExplorerToggle() {
  const open = useWorkspace((s) => s.explorerOpen && !s.focusMode);
  const toggle = useWorkspace((s) => s.toggleExplorer);
  return (
    <button
      type="button"
      className={styles.toggle}
      data-testid="toggle-explorer"
      title="Explorer (⌘B)"
      aria-label="Explorer"
      aria-pressed={open}
      onClick={toggle}
    >
      <FolderIcon size={16} />
    </button>
  );
}

function VariablesToggle() {
  const open = useWorkspace((s) => s.rightPanel === "variables" && !s.focusMode);
  const toggle = useWorkspace((s) => s.toggleRightPanel);
  return (
    <button
      type="button"
      className={styles.toggle}
      data-testid="toggle-variables"
      title="Variables"
      aria-label="Variables"
      aria-pressed={open}
      onClick={() => toggle("variables")}
    >
      <VariablesIcon size={16} />
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
      <FocusIcon size={16} />
    </button>
  );
}

export function Banner({ entry }: { entry: NotebookEntry | null }) {
  return (
    <header className={styles.banner} aria-label="Notisbook">
      <BrandMark size={32} />
      <span className={styles.wordmark}>notisbook</span>
      <span className={styles.tagline}>Explore. Code. Transform.</span>
      <span className={styles.separator} aria-hidden="true" />
      <MenuBar entry={entry} />
      <div className={styles.actions}>
        {entry ? (
          <NotebookProvider entry={entry}>
            <SystemResources />
            <SaveState />
          </NotebookProvider>
        ) : null}
        <ExplorerToggle />
        <VariablesToggle />
        <FocusToggle />
      </div>
    </header>
  );
}
