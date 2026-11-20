/**
 * Árvore somente leitura do bucket Notislake (padrão ARIA "tree" plana, como o
 * `FileTree`). Cada prefixo é listado ao expandir; páginas extras vêm pela linha
 * "Load more…". A única ação é copiar o caminho `s3a://<bucket>/<chave>`.
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
import {
  isNotislakeTreeAvailable,
  useNotislake,
  type NotislakeDirState,
} from "../../state/notislake";
import { ContextMenu } from "../shell/ContextMenu";
import type { MenuItem } from "../shell/Menu";
import { ChevronRightIcon, FileIcon } from "../shell/icons";
import styles from "./DataPanel.module.css";
import { INDENT_PX, treeIndent } from "./treeIndent";

interface TreeNode {
  /** Chave S3 completa; pastas terminam em "/". */
  key: string;
  name: string;
  isDir: boolean;
  /** Tamanho em bytes; só para arquivos. */
  bytes?: number;
}

type Row =
  | { kind: "node"; rowKey: string; node: TreeNode; level: number; dir: string; pos: number; size: number }
  | { kind: "more"; rowKey: string; dir: string; level: number }
  | { kind: "status"; rowKey: string; level: number; text: string; error: boolean; retryDir?: string };

type NavRow = Exclude<Row, { kind: "status" }>;

interface MenuState {
  x: number;
  y: number;
  node: TreeNode;
  origin: HTMLElement | null;
}

interface Feedback {
  text: string;
  error: boolean;
}

const FEEDBACK_MS = 2000;
const ERROR_FEEDBACK_MS = 6000;
const SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"];
/** Pastas da raiz exibidas atenuadas (área de pouso, fora das camadas). */
const MUTED_ROOT_DIRS = new Set(["landing"]);
/**
 * Pastas da raiz sempre exibidas, nesta ordem, mesmo sem o prefixo no bucket (o bootstrap só cria
 * as camadas). São só de exibição: expandir uma pasta inexistente lista vazio.
 */
const FIXED_ROOT_DIRS = ["landing", "bronze", "silver", "gold"];

function baseName(key: string, dir: string): string {
  const rest = key.startsWith(dir) ? key.slice(dir.length) : key;
  return rest.endsWith("/") ? rest.slice(0, -1) : rest;
}

function formatSize(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${SIZE_UNITS[unit]}`;
}

/**
 * Pastas primeiro, depois objetos; marcadores de pasta (chave igual ao prefixo ou terminada em "/") ficam de fora.
 * Na raiz (sem erro de listagem), `FIXED_ROOT_DIRS` vêm antes, e as demais pastas seguem na ordem da listagem.
 */
function childrenOf(dir: string, state: NotislakeDirState): TreeNode[] {
  const fixed: TreeNode[] =
    dir === "" && !state.error ? FIXED_ROOT_DIRS.map((name) => ({ key: `${name}/`, name, isDir: true })) : [];
  const fixedKeys = new Set(fixed.map((n) => n.key));
  const folders = state.prefixes
    .filter((key) => !fixedKeys.has(key))
    .map((key) => ({ key, name: baseName(key, dir), isDir: true }));
  const files = state.objects
    .filter((o) => o.key !== dir && !o.key.endsWith("/"))
    .map((o) => ({ key: o.key, name: baseName(o.key, dir), isDir: false, bytes: o.size }));
  return [...fixed, ...folders, ...files];
}

function buildRows(
  dir: string,
  level: number,
  dirs: Record<string, NotislakeDirState>,
  expanded: Record<string, true>,
  out: Row[],
): void {
  const state = dirs[dir];
  if (!state) return;
  const nodes = childrenOf(dir, state);
  nodes.forEach((node, i) => {
    out.push({
      kind: "node",
      rowKey: `${node.isDir ? "dir" : "obj"}:${node.key}`,
      node,
      level,
      dir,
      pos: i + 1,
      size: nodes.length,
    });
    if (node.isDir && expanded[node.key]) buildRows(node.key, level + 1, dirs, expanded, out);
  });
  if (state.loading) {
    out.push({ kind: "status", rowKey: `loading:${dir}`, level, text: "Loading…", error: false });
  } else if (state.error) {
    out.push({ kind: "status", rowKey: `error:${dir}`, level, text: state.error, error: true, retryDir: dir });
  } else if (nodes.length === 0 && state.nextToken === null) {
    out.push({ kind: "status", rowKey: `empty:${dir}`, level, text: "Empty", error: false });
  }
  if (state.nextToken !== null && !state.loading) {
    out.push({ kind: "more", rowKey: `more:${dir}`, dir, level });
  }
}

/** Pasta em traço fino e cantos retos (CSS `.fold`); objeto com o ícone de arquivo. */
function NodeIcon({ node }: { node: TreeNode }): ReactNode {
  return node.isDir ? <span className={styles.fold} aria-hidden="true" /> : <FileIcon size={14} />;
}

export function NotislakeTree() {
  const dirs = useNotislake((s) => s.dirs);
  const expanded = useNotislake((s) => s.expanded);
  const bucket = useNotislake((s) => s.bucket);
  const available = useNotislake((s) => isNotislakeTreeAvailable(s.status));
  const hasRoot = useNotislake((s) => s.dirs[""] !== undefined);
  const { toggle, expand, collapse, loadMore, loadRoot, refresh } = useNotislake.getState();
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  useEffect(() => {
    // `hasRoot` volta a false após `reset()` (troca de conexão) e recarrega a raiz.
    if (available && !hasRoot) loadRoot();
  }, [available, hasRoot, loadRoot]);

  useEffect(() => {
    if (!feedback) return;
    const t = window.setTimeout(() => setFeedback(null), feedback.error ? ERROR_FEEDBACK_MS : FEEDBACK_MS);
    return () => window.clearTimeout(t);
  }, [feedback]);

  async function copyUri(node: TreeNode) {
    if (!bucket) {
      setFeedback({ text: "Could not copy", error: true });
      return;
    }
    try {
      await navigator.clipboard.writeText(`s3a://${bucket}/${node.key}`);
      setFeedback({ text: "Path copied", error: false });
    } catch {
      setFeedback({ text: "Could not copy", error: true });
    }
  }

  function openMenu(node: TreeNode, x: number, y: number, origin: HTMLElement | null) {
    setMenu({ x, y, node, origin });
  }

  function openMenuAtRow(node: TreeNode, rowKey: string) {
    const el = refs.current.get(rowKey);
    if (!el) return;
    const r = el.getBoundingClientRect();
    openMenu(node, r.left + INDENT_PX, r.bottom, el);
  }

  function onContextMenu(e: MouseEvent<HTMLDivElement>, node: TreeNode) {
    e.preventDefault();
    // Tecla ContextMenu em alguns navegadores gera o evento sem coordenadas.
    if (e.clientX === 0 && e.clientY === 0) {
      const r = e.currentTarget.getBoundingClientRect();
      openMenu(node, r.left + INDENT_PX, r.bottom, e.currentTarget);
    } else {
      openMenu(node, e.clientX, e.clientY, e.currentTarget);
    }
  }

  const menuItems = (node: TreeNode): MenuItem[] => [
    {
      label: "Copy s3a:// path",
      onSelect: () => void copyUri(node),
      testId: "notislake-copy-s3a-path",
    },
  ];

  const rows: Row[] = [];
  buildRows("", 1, dirs, expanded, rows);
  const nav = rows.filter((r): r is NavRow => r.kind !== "status");
  const navIndex = new Map(nav.map((r, i) => [r.rowKey, i]));
  const activeKey = nav.some((r) => r.rowKey === focusKey) ? focusKey : (nav[0]?.rowKey ?? null);

  const focusRow = (key: string | undefined) => {
    if (key) refs.current.get(key)?.focus();
  };

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>, row: NavRow, index: number) {
    const node = row.kind === "node" ? row.node : null;
    switch (e.key) {
      case "ArrowDown":
        focusRow(nav[index + 1]?.rowKey);
        break;
      case "ArrowUp":
        focusRow(nav[index - 1]?.rowKey);
        break;
      case "Home":
        focusRow(nav[0]?.rowKey);
        break;
      case "End":
        focusRow(nav[nav.length - 1]?.rowKey);
        break;
      case "ArrowRight":
        if (node?.isDir) {
          if (!expanded[node.key]) expand(node.key);
          else {
            const next = nav[index + 1];
            if (next && next.level > row.level) focusRow(next.rowKey);
          }
        }
        break;
      case "ArrowLeft":
        if (node?.isDir && expanded[node.key]) collapse(node.key);
        else if (row.dir !== "") focusRow(`dir:${row.dir}`);
        break;
      case "ContextMenu":
        if (node) openMenuAtRow(node, row.rowKey);
        break;
      case "F10":
        if (!e.shiftKey) return;
        if (node) openMenuAtRow(node, row.rowKey);
        break;
      case "Enter":
      case " ":
        if (node?.isDir) toggle(node.key);
        else if (row.kind === "more") loadMore(row.dir);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  return (
    <>
      <div className={styles.treeBody} role="tree" aria-label="Notislake objects">
        {rows.map((row) => {
          const indent = treeIndent(row.level);
          if (row.kind === "status") {
            return (
              <div
                key={row.rowKey}
                role="presentation"
                className={`${styles.treeStatus} ${styles.treeGuides} ${row.error ? styles.treeError : ""}`}
                style={indent}
              >
                {row.text}
                {row.retryDir !== undefined ? (
                  <button type="button" className={`btn btn-ghost ${styles.treeRetry}`} onClick={() => refresh(row.retryDir)}>
                    Retry
                  </button>
                ) : null}
              </div>
            );
          }
          const index = navIndex.get(row.rowKey) ?? -1;
          const common = {
            ref: (el: HTMLDivElement | null) => {
              if (el) refs.current.set(row.rowKey, el);
              else refs.current.delete(row.rowKey);
            },
            className: `${styles.treeRow} ${styles.treeGuides}`,
            style: indent,
            tabIndex: row.rowKey === activeKey ? 0 : -1,
            onFocus: () => setFocusKey(row.rowKey),
            onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => onKeyDown(e, row, index),
          };
          if (row.kind === "more") {
            return (
              <div
                key={row.rowKey}
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
          const { node } = row;
          const isOpen = node.isDir && Boolean(expanded[node.key]);
          const size = node.isDir ? null : node.bytes;
          const muted = node.isDir && row.dir === "" && MUTED_ROOT_DIRS.has(node.name);
          return (
            <div
              key={row.rowKey}
              role="treeitem"
              aria-level={row.level}
              aria-posinset={row.pos}
              aria-setsize={row.size}
              aria-expanded={node.isDir ? isOpen : undefined}
              aria-selected={row.rowKey === focusKey}
              title={node.key}
              {...common}
              className={muted ? `${common.className} ${styles.treeMuted}` : common.className}
              onContextMenu={(e) => onContextMenu(e, node)}
              onClick={() => {
                setFocusKey(row.rowKey);
                if (node.isDir) toggle(node.key);
              }}
            >
              <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ""}`} aria-hidden="true">
                {node.isDir ? <ChevronRightIcon size={12} /> : null}
              </span>
              <span className={styles.treeIcon}>
                <NodeIcon node={node} />
              </span>
              <span className={styles.treeName}>{node.name}</span>
              {size !== null && size !== undefined ? (
                <span className={styles.treeSize}>{formatSize(size)}</span>
              ) : null}
            </div>
          );
        })}
      </div>
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems(menu.node)}
          ariaLabel={`Actions for ${menu.node.name}`}
          onClose={closeMenu}
          returnFocusTo={menu.origin}
        />
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
