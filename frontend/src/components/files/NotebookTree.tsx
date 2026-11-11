/**
 * Árvore do painel Notebooks (ARIA "tree" plana: `aria-level` em vez de grupos aninhados).
 * Mostra pastas e notebooks; clicar em pasta expande/recolhe, em notebook abre a aba.
 * Foco por roving tabindex. Rename e rascunho de nova pasta usam `NameInput` inline.
 */
import { type KeyboardEvent, type MouseEvent, useCallback, useMemo, useRef, useState } from "react";
import type { ContentEntry } from "../../api";
import { uniqueName } from "../../lib/paths";
import { type DirState, useNotebookTree } from "../../state/notebookTree";
import { activeNotebookPath, openNotebook, useRouter } from "../../state/router";
import { useWorkspace } from "../../state/workspace";
import { ContextMenu } from "../shell/ContextMenu";
import { ChevronRightIcon, FolderIcon, NotebookIcon } from "../shell/icons";
import styles from "./FileBrowser.module.css";
import { formatAbsolute, formatRelative, formatSize } from "./format";
import { NameInput } from "./NameInput";

export type Draft = { kind: "create"; dir: string } | { kind: "rename"; path: string } | null;

export interface NotebookTreeProps {
  draft: Draft;
  onCreate: (dir: string, name: string) => Promise<void>;
  onRename: (entry: ContentEntry, name: string) => Promise<void>;
  onCancelDraft: () => void;
  onStartRename: (entry: ContentEntry) => void;
  onDelete: (entry: ContentEntry) => void;
}

type Row =
  | { kind: "entry"; key: string; entry: ContentEntry; level: number; dir: string }
  | { kind: "draft"; key: string; level: number; dir: string }
  | { kind: "status"; key: string; level: number; text: string };

type RowMenu = { x: number; y: number; entry: ContentEntry; origin: HTMLElement };

const INDENT_PX = 14;
const BASE_PAD_PX = 8;

function describe(entry: ContentEntry): string {
  const parts = [entry.name, `Modified: ${formatAbsolute(entry.mtime)} (${formatRelative(entry.mtime)})`];
  if (entry.type !== "dir") parts.push(`Size: ${formatSize(entry.size)}`);
  return parts.join("\n");
}

function buildRows(
  dir: string,
  level: number,
  dirs: Record<string, DirState>,
  expanded: Record<string, true>,
  draft: Draft,
  out: Row[],
): void {
  const state = dirs[dir];
  if (draft?.kind === "create" && draft.dir === dir) out.push({ kind: "draft", key: `draft:${dir}`, level, dir });
  if (!state) return;
  // Arquivos comuns ficam escondidos; a listagem completa segue no store para `uniqueName`.
  const visible = state.entries.filter((e) => e.type !== "file");
  for (const entry of visible) {
    out.push({ kind: "entry", key: entry.path, entry, level, dir });
    if (entry.type === "dir" && expanded[entry.path]) buildRows(entry.path, level + 1, dirs, expanded, draft, out);
  }
  if (state.status === "loading" && state.entries.length === 0) {
    out.push({ kind: "status", key: `loading:${dir}`, level, text: "Loading…" });
  } else if (state.status === "error" && dir !== "") {
    out.push({ kind: "status", key: `error:${dir}`, level, text: `Could not list: ${state.error ?? "error"}` });
  } else if (state.status === "ready" && visible.length === 0 && dir !== "" && !(draft?.kind === "create" && draft.dir === dir)) {
    out.push({ kind: "status", key: `empty:${dir}`, level, text: "Empty" });
  }
}

export function NotebookTree({ draft, onCreate, onRename, onCancelDraft, onStartRename, onDelete }: NotebookTreeProps) {
  const dirs = useNotebookTree((s) => s.dirs);
  const expanded = useNotebookTree((s) => s.expanded);
  const selected = useNotebookTree((s) => s.selected);
  const { toggle, expand, collapse, select } = useNotebookTree.getState();
  const tabs = useWorkspace((s) => s.tabs);
  const root = useWorkspace((s) => s.root);
  const activePath = useRouter((s) => activeNotebookPath(s.route));
  const openSet = useMemo(() => new Set(tabs), [tabs]);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [menu, setMenu] = useState<RowMenu | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());
  const closeMenu = useCallback(() => setMenu(null), []);

  const rows: Row[] = [];
  buildRows("", 1, dirs, expanded, draft, rows);
  const nav = rows.filter((r): r is Extract<Row, { kind: "entry" }> => r.kind === "entry");
  const activeKey = nav.some((r) => r.key === focusKey) ? focusKey : (nav[0]?.key ?? null);
  const rootEmpty = dirs[""]?.status === "ready" && rows.length === 0;

  const focusRow = (key: string | undefined) => {
    if (key) refs.current.get(key)?.focus();
  };

  function activate(entry: ContentEntry) {
    select({ path: entry.path, type: entry.type });
    if (entry.type === "dir") toggle(entry.path);
    else if (entry.type === "notebook") openNotebook(entry.path);
  }

  function openMenuAt(entry: ContentEntry, el: HTMLElement, x: number, y: number) {
    select({ path: entry.path, type: entry.type });
    setMenu({ x, y, entry, origin: el });
  }

  function onContextMenu(e: MouseEvent<HTMLDivElement>, entry: ContentEntry) {
    e.preventDefault();
    // Tecla ContextMenu em alguns navegadores gera o evento sem coordenadas.
    if (e.clientX === 0 && e.clientY === 0) {
      const r = e.currentTarget.getBoundingClientRect();
      openMenuAt(entry, e.currentTarget, r.left + INDENT_PX, r.bottom);
    } else {
      openMenuAt(entry, e.currentTarget, e.clientX, e.clientY);
    }
  }

  function openMenuAtRow(entry: ContentEntry) {
    const el = refs.current.get(entry.path);
    if (!el) return;
    const r = el.getBoundingClientRect();
    openMenuAt(entry, el, r.left + INDENT_PX, r.bottom);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>, row: Extract<Row, { kind: "entry" }>, index: number) {
    // Teclas digitadas no NameInput não são da árvore.
    if (e.target !== e.currentTarget) return;
    const { entry } = row;
    const isDir = entry.type === "dir";
    switch (e.key) {
      case "ArrowDown":
        focusRow(nav[index + 1]?.key);
        break;
      case "ArrowUp":
        focusRow(nav[index - 1]?.key);
        break;
      case "Home":
        focusRow(nav[0]?.key);
        break;
      case "End":
        focusRow(nav[nav.length - 1]?.key);
        break;
      case "ArrowRight":
        if (isDir) {
          if (!expanded[entry.path]) expand(entry.path);
          else {
            const next = nav[index + 1];
            if (next && next.level > row.level) focusRow(next.key);
          }
        }
        break;
      case "ArrowLeft":
        if (isDir && expanded[entry.path]) collapse(entry.path);
        else if (row.dir !== "") focusRow(row.dir);
        break;
      case "ContextMenu":
        openMenuAtRow(entry);
        break;
      case "F10":
        if (!e.shiftKey) return;
        openMenuAtRow(entry);
        break;
      case "Enter":
      case " ":
        activate(entry);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  function indent(level: number) {
    return { paddingLeft: `${BASE_PAD_PX + (level - 1) * INDENT_PX}px` };
  }

  return (
    <>
      <div
        className={styles.tree}
        role="tree"
        aria-label={`Notebooks in ${root?.name ?? "root"}`}
        onClick={(e) => {
          if (e.target === e.currentTarget) select(null);
        }}
      >
        {rows.map((row) => {
          if (row.kind === "status") {
            return (
              <div key={row.key} role="presentation" className={styles.treeStatus} style={indent(row.level + 1)}>
                {row.text}
              </div>
            );
          }
          if (row.kind === "draft") {
            return (
              <div key={row.key} role="presentation" className={styles.row} data-editing="" style={indent(row.level)}>
                <span className={styles.chevron} aria-hidden="true" />
                <FolderIcon size={14} className={styles.iconDir} />
                <NameInput
                  label="New folder name"
                  initial={uniqueName(
                    (dirs[row.dir]?.entries ?? []).map((e) => e.name),
                    "New folder",
                    "",
                  )}
                  onSubmit={(name) => onCreate(row.dir, name)}
                  onCancel={onCancelDraft}
                />
              </div>
            );
          }
          const { entry } = row;
          const index = nav.findIndex((r) => r.key === row.key);
          const isDir = entry.type === "dir";
          const isOpen = isDir && Boolean(expanded[entry.path]);
          const renaming = draft?.kind === "rename" && draft.path === entry.path;
          const isSelected = selected?.path === entry.path;
          return (
            <div
              key={row.key}
              ref={(el) => {
                if (el) refs.current.set(row.key, el);
                else refs.current.delete(row.key);
              }}
              role="treeitem"
              aria-level={row.level}
              aria-expanded={isDir ? isOpen : undefined}
              aria-selected={isSelected}
              className={styles.row}
              style={indent(row.level)}
              tabIndex={row.key === activeKey ? 0 : -1}
              title={renaming ? undefined : describe(entry)}
              data-openable
              data-entry-type={entry.type}
              data-editing={renaming || undefined}
              data-open={openSet.has(entry.path) || undefined}
              data-active={entry.path === activePath || undefined}
              data-selected={isSelected || undefined}
              onFocus={() => setFocusKey(row.key)}
              onKeyDown={(e) => onKeyDown(e, row, index)}
              onContextMenu={renaming ? undefined : (e) => onContextMenu(e, entry)}
              onClick={renaming ? undefined : () => activate(entry)}
            >
              <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ""}`} aria-hidden="true">
                {isDir ? <ChevronRightIcon size={12} /> : null}
              </span>
              {isDir ? <FolderIcon size={14} className={styles.iconDir} /> : <NotebookIcon size={14} className={styles.iconNotebook} />}
              {renaming ? (
                <NameInput
                  key={`rename-${entry.path}`}
                  label={`New name for ${entry.name}`}
                  initial={entry.name}
                  onSubmit={(name) => onRename(entry, name)}
                  onCancel={onCancelDraft}
                />
              ) : (
                <span className={styles.treeName}>{entry.name}</span>
              )}
            </div>
          );
        })}
        {rootEmpty && draft === null ? (
          <p className={styles.empty}>Empty folder. Use File → New notebook to get started.</p>
        ) : null}
      </div>
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          ariaLabel={`Actions for ${menu.entry.name}`}
          items={[
            { label: "Rename", onSelect: () => onStartRename(menu.entry) },
            { label: "Delete", danger: true, onSelect: () => onDelete(menu.entry) },
          ]}
          onClose={closeMenu}
          returnFocusTo={menu.origin}
        />
      ) : null}
    </>
  );
}
