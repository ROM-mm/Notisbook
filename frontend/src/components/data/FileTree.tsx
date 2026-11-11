/**
 * Árvore de arquivos (padrão ARIA "tree" plana: `aria-level` em vez de grupos
 * aninhados). Cada diretório é carregado ao expandir; páginas extras vêm pela
 * linha "Carregar mais". Foco por roving tabindex.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { deleteDir, deleteDirMessage, type FsEntry } from "../../api/files";
import { dirname } from "../../lib/paths";
import { useFiles, type DirState } from "../../state/files";
import { useNotebookTree } from "../../state/notebookTree";
import { isOpenUnder, useWorkspace } from "../../state/workspace";
import { ConfirmDialog } from "../shell/ConfirmDialog";
import { ContextMenu } from "../shell/ContextMenu";
import type { MenuItem } from "../shell/Menu";
import {
  ChevronRightIcon,
  DeltaIcon,
  FileCsvIcon,
  FileIcon,
  FileJsonIcon,
  FileParquetIcon,
  FolderIcon,
  SymlinkIcon,
} from "../shell/icons";
import styles from "./DataPanel.module.css";

type Row =
  | {
      kind: "entry";
      key: string;
      entry: FsEntry;
      level: number;
      dir: string;
      pos: number;
      size: number;
    }
  | { kind: "more"; key: string; dir: string; level: number }
  | {
      kind: "status";
      key: string;
      level: number;
      text: string;
      error: boolean;
    };

const INDENT_PX = 14;
const FEEDBACK_MS = 2000;
/** Erros (ex.: tabelas do catálogo na pasta) são mais longos que "Path copied". */
const ERROR_FEEDBACK_MS = 6000;

interface MenuState {
  x: number;
  y: number;
  entry: FsEntry;
  origin: HTMLElement | null;
}

interface Feedback {
  text: string;
  error: boolean;
}

/** Atualiza a árvore de notebooks quando a pasta excluída está sob a raiz dos notebooks. */
function syncNotebookTree(path: string): void {
  const root = useWorkspace.getState().root?.path;
  if (!root || !path.startsWith(`${root.replace(/\/+$/, "")}/`)) return;
  const rel = path.slice(root.replace(/\/+$/, "").length + 1);
  const tree = useNotebookTree.getState();
  tree.forget(rel);
  void tree.reload(dirname(rel));
}

/** Há aba de notebook aberta dentro de `path` (absoluto)? As abas usam caminho relativo à raiz dos notebooks. */
function hasOpenNotebookUnder(path: string): boolean {
  const { root, tabs } = useWorkspace.getState();
  if (!root) return false;
  const base = root.path.replace(/\/+$/, "");
  if (path === base || base.startsWith(`${path}/`)) return tabs.length > 0;
  return path.startsWith(`${base}/`) && isOpenUnder(path.slice(base.length + 1));
}

/** Caminho relativo à raiz escolhida; a própria raiz vira ".". */
function relativeToRoot(root: string, path: string): string {
  if (path === root) return ".";
  const base = root.endsWith("/") ? root : `${root}/`;
  return path.startsWith(base) ? path.slice(base.length) : path;
}

function extension(name: string): string {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i + 1).toLowerCase() : "";
}

function EntryIcon({ entry }: { entry: FsEntry }): ReactNode {
  const ext = extension(entry.name);
  if (entry.is_dir) {
    if (entry.name === "_delta_log" || ext === "delta")
      return <DeltaIcon size={14} />;
    if (entry.is_symlink) return <SymlinkIcon size={14} />;
    return <FolderIcon size={14} />;
  }
  if (entry.is_symlink) return <SymlinkIcon size={14} />;
  if (ext === "parquet" || ext === "orc" || ext === "avro")
    return <FileParquetIcon size={14} />;
  if (ext === "csv" || ext === "tsv") return <FileCsvIcon size={14} />;
  if (ext === "json" || ext === "jsonl" || ext === "ndjson")
    return <FileJsonIcon size={14} />;
  if (ext === "delta") return <DeltaIcon size={14} />;
  return <FileIcon size={14} />;
}

function buildRows(
  dir: string,
  level: number,
  dirs: Record<string, DirState>,
  expanded: Record<string, true>,
  out: Row[],
): void {
  const state = dirs[dir];
  if (!state) return;
  state.entries.forEach((entry, i) => {
    out.push({
      kind: "entry",
      key: entry.path,
      entry,
      level,
      dir,
      pos: i + 1,
      size: state.entries.length,
    });
    if (entry.is_dir && expanded[entry.path])
      buildRows(entry.path, level + 1, dirs, expanded, out);
  });
  if (state.loading)
    out.push({
      kind: "status",
      key: `loading:${dir}`,
      level,
      text: "Loading…",
      error: false,
    });
  else if (state.error)
    out.push({
      kind: "status",
      key: `error:${dir}`,
      level,
      text: state.error,
      error: true,
    });
  else if (state.entries.length === 0)
    out.push({
      kind: "status",
      key: `empty:${dir}`,
      level,
      text: "Empty",
      error: false,
    });
  if (state.nextOffset !== null && !state.loading)
    out.push({ kind: "more", key: `more:${dir}`, dir, level });
}

export function FileTree({ root }: { root: string }) {
  const dirs = useFiles((s) => s.dirs);
  const expanded = useFiles((s) => s.expanded);
  const { toggle, expand, collapse, loadMore } = useFiles.getState();
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [removing, setRemoving] = useState<FsEntry | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  useEffect(() => {
    if (!feedback) return;
    const t = window.setTimeout(() => setFeedback(null), feedback.error ? ERROR_FEEDBACK_MS : FEEDBACK_MS);
    return () => window.clearTimeout(t);
  }, [feedback]);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setFeedback({ text: "Path copied", error: false });
    } catch {
      setFeedback({ text: "Could not copy", error: true });
    }
  }

  async function removeDir(entry: FsEntry) {
    const parent = dirname(entry.path);
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      await deleteDir(entry.path);
      useFiles.getState().forget(entry.path);
      useFiles.getState().reload(parent);
      syncNotebookTree(entry.path);
      setRemoving(null);
    } catch (err) {
      // O diálogo fica aberto com o erro; a pasta pode já ter sumido (ou sido apagada em parte): a listagem
      // precisa refletir o disco.
      setRemoveError(deleteDirMessage(err));
      useFiles.getState().reload(parent);
    } finally {
      setRemoveBusy(false);
    }
  }

  function requestRemove(entry: FsEntry) {
    if (hasOpenNotebookUnder(entry.path)) {
      setFeedback({
        text: `Close the notebook tabs inside “${entry.name}” before deleting it.`,
        error: true,
      });
      return;
    }
    setRemoveError(null);
    setRemoving(entry);
  }

  function openMenu(
    entry: FsEntry,
    x: number,
    y: number,
    origin: HTMLElement | null,
  ) {
    setMenu({ x, y, entry, origin });
  }

  function openMenuAtRow(entry: FsEntry, key: string) {
    const el = refs.current.get(key);
    if (!el) return;
    const r = el.getBoundingClientRect();
    openMenu(entry, r.left + INDENT_PX, r.bottom, el);
  }

  function onContextMenu(e: MouseEvent<HTMLDivElement>, entry: FsEntry) {
    e.preventDefault();
    // Tecla ContextMenu em alguns navegadores gera o evento sem coordenadas.
    if (e.clientX === 0 && e.clientY === 0) {
      const r = e.currentTarget.getBoundingClientRect();
      openMenu(entry, r.left + INDENT_PX, r.bottom, e.currentTarget);
    } else {
      openMenu(entry, e.clientX, e.clientY, e.currentTarget);
    }
  }

  const menuItems = (entry: FsEntry): MenuItem[] => [
    {
      label: "Copy Path",
      onSelect: () => void copy(entry.path),
      testId: "files-copy-path",
    },
    {
      label: "Copy Relative Path",
      onSelect: () => void copy(relativeToRoot(root, entry.path)),
      testId: "files-copy-relative-path",
    },
    ...(entry.is_dir
      ? [
          "separator" as const,
          {
            label: "Delete Folder…",
            danger: true,
            onSelect: () => requestRemove(entry),
            testId: "files-delete-folder",
          },
        ]
      : []),
  ];

  const rows: Row[] = [];
  buildRows(root, 1, dirs, expanded, rows);
  const nav = rows.filter((r) => r.kind !== "status");
  const activeKey = nav.some((r) => r.key === focusKey)
    ? focusKey
    : (nav[0]?.key ?? null);

  const focusRow = (key: string | undefined) => {
    if (key) refs.current.get(key)?.focus();
  };

  function onKeyDown(
    e: KeyboardEvent<HTMLDivElement>,
    row: Exclude<Row, { kind: "status" }>,
    index: number,
  ) {
    const entry = row.kind === "entry" ? row.entry : null;
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
        if (entry?.is_dir) {
          if (!expanded[entry.path]) expand(entry.path);
          else {
            const next = nav[index + 1];
            if (next && next.level > row.level) focusRow(next.key);
          }
        }
        break;
      case "ArrowLeft":
        if (entry?.is_dir && expanded[entry.path]) collapse(entry.path);
        else if (row.dir !== root) focusRow(row.dir);
        break;
      case "ContextMenu":
        if (entry) openMenuAtRow(entry, row.key);
        break;
      case "F10":
        if (!e.shiftKey) return;
        if (entry) openMenuAtRow(entry, row.key);
        break;
      case "Enter":
      case " ":
        if (entry?.is_dir) toggle(entry.path);
        else if (row.kind === "more") loadMore(row.dir);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  return (
    <>
      <div
        className={styles.treeBody}
        role="tree"
        aria-label={`Files in ${root}`}
      >
        {rows.map((row) => {
          const indent = { paddingLeft: `${row.level * INDENT_PX}px` };
          if (row.kind === "status") {
            return (
              <div
                key={row.key}
                role="presentation"
                className={`${styles.treeStatus} ${row.error ? styles.treeError : ""}`}
                style={indent}
              >
                {row.text}
              </div>
            );
          }
          const index = nav.findIndex((r) => r.key === row.key);
          const common = {
            ref: (el: HTMLDivElement | null) => {
              if (el) refs.current.set(row.key, el);
              else refs.current.delete(row.key);
            },
            className: styles.treeRow,
            style: indent,
            tabIndex: row.key === activeKey ? 0 : -1,
            onFocus: () => setFocusKey(row.key),
            onKeyDown: (e: KeyboardEvent<HTMLDivElement>) =>
              onKeyDown(e, row, index),
          };
          if (row.kind === "more") {
            return (
              <div
                key={row.key}
                role="treeitem"
                aria-level={row.level}
                aria-selected={false}
                {...common}
                onClick={() => loadMore(row.dir)}
              >
                <span className={styles.treeMore}>Load more…</span>
              </div>
            );
          }
          const { entry } = row;
          const isOpen = entry.is_dir && Boolean(expanded[entry.path]);
          return (
            <div
              key={row.key}
              role="treeitem"
              aria-level={row.level}
              aria-posinset={row.pos}
              aria-setsize={row.size}
              aria-expanded={entry.is_dir ? isOpen : undefined}
              aria-selected={row.key === focusKey}
              title={entry.path}
              data-path={entry.path}
              {...common}
              onContextMenu={(e) => onContextMenu(e, entry)}
              onClick={() => {
                setFocusKey(row.key);
                if (entry.is_dir) toggle(entry.path);
              }}
            >
              <span
                className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ""}`}
                aria-hidden="true"
              >
                {entry.is_dir ? <ChevronRightIcon size={12} /> : null}
              </span>
              <span className={styles.treeIcon}>
                <EntryIcon entry={entry} />
              </span>
              <span className={styles.treeName}>{entry.name}</span>
            </div>
          );
        })}
      </div>
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems(menu.entry)}
          ariaLabel={`Actions for ${menu.entry.name}`}
          onClose={closeMenu}
          returnFocusTo={menu.origin}
        />
      ) : null}
      {removing ? (
        <ConfirmDialog
          title={removing.is_symlink ? "Remove link" : "Delete folder"}
          confirmLabel={removing.is_symlink ? "Remove" : "Delete"}
          busyLabel={removing.is_symlink ? "Removing…" : "Deleting…"}
          danger
          busy={removeBusy}
          error={removeError}
          onConfirm={() => void removeDir(removing)}
          onCancel={() => {
            setRemoving(null);
            setRemoveError(null);
          }}
          testId="files-delete-folder-dialog"
        >
          {removing.is_symlink ? (
            <p>
              Remove the link <code>{removing.name}</code>? The target folder is kept.
            </p>
          ) : (
            <p>
              Delete folder <code>{removing.name}</code> and everything in it? This cannot be undone.
            </p>
          )}
        </ConfirmDialog>
      ) : null}
      <div
        className={`${styles.copyFeedback} ${feedback?.error ? styles.treeError : ""}`}
        role="status"
        aria-live="polite"
      >
        {feedback?.text}
      </div>
    </>
  );
}
