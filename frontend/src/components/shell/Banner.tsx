/**
 * Header do shell: marca, menubar e, à direita, estado de salvamento e os
 * toggles das laterais esquerda (⌘B) e direita (⌥⌘B) e modo foco (⌘.). Recebe a aba
 * ativa para os menus e o estado de salvamento.
 */
import { NotebookProvider, useNotebook } from "../../state/notebookContext";
import type { NotebookEntry } from "../../state/workspace";
import { useWorkspace } from "../../state/workspace";
import styles from "./Banner.module.css";
import { BrandMark, FocusIcon, PanelLeftIcon, PanelRightIcon } from "./icons";
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
      {left ? <PanelLeftIcon size={16} /> : <PanelRightIcon size={16} />}
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
        <PanelToggle side="left" />
        <PanelToggle side="right" />
        <FocusToggle />
      </div>
    </header>
  );
}
