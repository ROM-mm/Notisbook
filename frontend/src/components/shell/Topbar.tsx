/**
 * Barra superior (`data-testid="notebook-topbar"`).
 * Com notebook: linha única — menus File / Edit / View / Run / Help e About
 * à esquerda; à direita status do kernel, seletor de ambiente, aviso de
 * salvamento (só Saving…/Save failed) e toggle de variáveis.
 * Sem notebook ativo (início/Settings) mostra o título e os itens de notebook
 * ficam desabilitados.
 */
import type { ReactNode } from "react";
import { exportNotebook, type ExportFormat } from "../../api/export";
import { saveBlob } from "../../lib/download";
import { basename, dirname } from "../../lib/paths";
import { type EditableCellType, type InsertWhere, toNotebook } from "../../state/notebook";
import { NotebookProvider, useNotebook } from "../../state/notebookContext";
import { type ThemePref, useTheme } from "../../state/theme";
import { getTargetDir } from "../../state/notebookTree";
import { createUntitledNotebook, type NotebookEntry, useWorkspace } from "../../state/workspace";
import { kernelAlive, kernelHasWork, kernelReady, KernelStatus } from "../kernel/KernelStatus";
import { KernelSelector } from "../kernel/KernelSelector";
import { FocusIcon, VariablesIcon } from "./icons";
import { Menu, type MenuItem } from "./Menu";
import { SystemResources } from "./SystemResources";
import styles from "./AppShell.module.css";

const THEMES: { pref: ThemePref; label: string }[] = [
  { pref: "light", label: "Light theme" },
  { pref: "dark", label: "Dark theme" },
  { pref: "system", label: "System theme" },
];

function newNotebook(entry: NotebookEntry | null): void {
  const dir = entry ? dirname(entry.path) : getTargetDir();
  createUntitledNotebook(dir).catch((err: unknown) =>
    window.alert(`Could not create the notebook: ${err instanceof Error ? err.message : String(err)}`),
  );
}

function exportAs(entry: NotebookEntry, format: ExportFormat): void {
  const doc = toNotebook(entry.notebook.getState());
  exportNotebook(format, doc, basename(entry.path))
    .then(({ blob, filename }) => saveBlob(blob, filename ?? `notebook.${format}`))
    .catch((err: unknown) =>
      window.alert(`Could not export the notebook: ${err instanceof Error ? err.message : String(err)}`),
    );
}

function insert(entry: NotebookEntry, where: InsertWhere, type: EditableCellType): void {
  const nb = entry.notebook.getState();
  const id = nb.insertCell(where, nb.activeId, type);
  nb.selectCell(id, "edit");
}

function fileItems(entry: NotebookEntry | null): MenuItem[] {
  const nb = entry?.notebook.getState();
  const ready = nb?.status === "ready";
  return [
    { label: "New notebook", onSelect: () => newNotebook(entry), testId: "menu-file-new" },
    {
      label: "Save",
      shortcut: "⌘S",
      disabled: !nb || nb.status !== "ready" || nb.saving,
      onSelect: () => void entry?.notebook.getState().save(),
      testId: "menu-file-save",
    },
    "separator",
    {
      label: "Export .ipynb",
      disabled: !ready,
      onSelect: () => entry && exportAs(entry, "ipynb"),
      testId: "menu-file-export-ipynb",
    },
    {
      label: "Export .py",
      disabled: !ready,
      onSelect: () => entry && exportAs(entry, "py"),
      testId: "menu-file-export-py",
    },
    {
      label: "Export .html",
      disabled: !ready,
      onSelect: () => entry && exportAs(entry, "html"),
      testId: "menu-file-export-html",
    },
    "separator",
    {
      label: "Close notebook",
      disabled: !entry,
      onSelect: () => entry && useWorkspace.getState().closeTab(entry.path),
    },
  ];
}

function editItems(entry: NotebookEntry | null): MenuItem[] {
  const nb = entry?.notebook.getState();
  const ready = nb?.status === "ready";
  const i = nb ? nb.cells.findIndex((c) => c.id === nb.activeId) : -1;
  const hasCell = ready && i >= 0;
  const id = nb?.activeId ?? null;
  return [
    { label: "Insert code cell above", shortcut: "A", disabled: !ready, onSelect: () => entry && insert(entry, "above", "code") },
    { label: "Insert code cell below", shortcut: "B", disabled: !ready, onSelect: () => entry && insert(entry, "below", "code") },
    { label: "Insert markdown below", disabled: !ready, onSelect: () => entry && insert(entry, "below", "markdown") },
    "separator",
    { label: "Move cell up", disabled: !hasCell || i === 0, onSelect: () => id && nb?.moveCell(id, -1) },
    {
      label: "Move cell down",
      disabled: !hasCell || i === (nb?.cells.length ?? 0) - 1,
      onSelect: () => id && nb?.moveCell(id, 1),
    },
    "separator",
    { label: "Delete cell", shortcut: "D D", danger: true, disabled: !hasCell, onSelect: () => id && nb?.deleteCell(id) },
  ];
}

function viewItems(): MenuItem[] {
  const { pref, setPref } = useTheme.getState();
  const themes = THEMES.map((t) => ({ label: t.label, checked: pref === t.pref, onSelect: () => setPref(t.pref), testId: `menu-view-${t.pref}` }));
  return [
    {
      label: "Focus mode",
      shortcut: "⌘.",
      checked: useWorkspace.getState().focusMode,
      onSelect: () => useWorkspace.getState().toggleFocusMode(),
      testId: "menu-view-focus",
    },
    "separator",
    ...themes,
  ];
}

function runItems(entry: NotebookEntry | null): MenuItem[] {
  const k = entry?.kernel.getState();
  const nb = entry?.notebook.getState();
  const alive = k ? kernelAlive(k) : false;
  const ready = k ? kernelReady(k) : false;
  const active = nb?.cells.find((c) => c.id === nb.activeId);
  const hasWork = k ? kernelHasWork(k) : false;
  return [
    {
      label: "Run cell",
      shortcut: "⇧↵",
      disabled: !alive || active?.cell_type !== "code",
      onSelect: () => active && entry?.kernel.getState().runCell(active.id),
    },
    { label: "Run all", disabled: !alive, onSelect: () => entry?.kernel.getState().runAll(), testId: "menu-run-all" },
    "separator",
    { label: "Interrupt", disabled: !alive || !hasWork, onSelect: () => entry?.kernel.getState().interrupt() },
    { label: "Restart kernel", disabled: !ready, onSelect: () => entry?.kernel.getState().restart() },
    { label: "Restart and run all", disabled: !ready, onSelect: () => entry?.kernel.getState().restartAndRunAll() },
  ];
}

function helpItems(): MenuItem[] {
  return [{ label: "Keyboard shortcuts", onSelect: () => useWorkspace.getState().setShortcutsOpen(true), testId: "menu-help-shortcuts" }];
}

function MenuBar({ entry }: { entry: NotebookEntry | null }) {
  return (
    <nav className={styles.menubar} aria-label="Menus">
      <Menu trigger="File" testId="menu-file" items={() => fileItems(entry)} />
      <Menu trigger="Edit" testId="menu-edit" items={() => editItems(entry)} />
      <Menu trigger="View" testId="menu-view" items={viewItems} />
      <Menu trigger="Run" testId="menu-run" items={() => runItems(entry)} />
      <Menu trigger="Help" testId="menu-help" items={helpItems} />
      <button
        type="button"
        className={styles.menuButton}
        data-testid="menu-about"
        aria-label="About Notisbook"
        onClick={() => useWorkspace.getState().setAboutOpen(true)}
      >About</button>
    </nav>
  );
}

function SaveState() {
  const saving = useNotebook((s) => s.saving);
  const saveError = useNotebook((s) => s.saveError);
  const ready = useNotebook((s) => s.status === "ready");
  if (!ready || (!saving && !saveError)) return null;
  const text = saving ? "Saving…" : "Save failed";
  return (
    <span className={saveError ? `${styles.saveText} ${styles.saveError}` : styles.saveText} title={saveError ?? undefined} data-testid="save-state">
      {text}
    </span>
  );
}

function VariablesToggle() {
  const open = useWorkspace((s) => s.rightPanel === "variables" && !s.focusMode);
  const toggle = useWorkspace((s) => s.toggleRightPanel);
  return (
    <button
      type="button"
      className={styles.topToggle}
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
      className={styles.topToggle}
      data-testid="toggle-focus"
      title="Focus mode"
      aria-label="Focus mode"
      aria-pressed={on}
      onClick={toggle}
    >
      <FocusIcon size={16} />
    </button>
  );
}

function NotebookActions() {
  return (
    <div className={styles.topActions}>
      <SystemResources />
      <KernelStatus />
      <KernelSelector />
      <SaveState />
      <FocusToggle />
      <VariablesToggle />
    </div>
  );
}

export function Topbar({ entry, title }: { entry: NotebookEntry | null; title: ReactNode | null }) {
  return (
    <header className={entry ? `${styles.topbar} ${styles.topbarSingle}` : styles.topbar} data-testid="notebook-topbar">
      {entry ? (
        <div className={styles.topRow}>
          <NotebookProvider entry={entry}>
            <MenuBar entry={entry} />
            <NotebookActions />
          </NotebookProvider>
        </div>
      ) : (
        <>
          {title ? (
            <div className={styles.topRow}>
              <div className={styles.titleRow}>
                <h1 className={styles.title}>{title}</h1>
              </div>
            </div>
          ) : null}
          <div className={styles.topRow}>
            <MenuBar entry={entry} />
            <div className={styles.topActions}>
              <FocusToggle />
            </div>
          </div>
        </>
      )}
    </header>
  );
}
