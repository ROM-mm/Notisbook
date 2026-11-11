/**
 * Painel Variables (direita do conteúdo): variáveis do kernel do notebook
 * ativo em árvore plana ARIA. Só monta com o painel aberto, e é a montagem
 * que liga as leituras: sem painel aberto nenhuma requisição é feita.
 */
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { useStore } from "zustand";
import type { VariableChild, VariableItem, VariablePathStep } from "../../api/types";
import { DEFAULT_VARIABLES_WIDTH, useLayout } from "../../state/layout";
import { activeNotebookPath, useRouter } from "../../state/router";
import {
  CHILDREN_PAGE,
  pathKey,
  SPECIAL_KEY,
  useVariables,
  VARIABLES_MAX_RETRIES,
  type ChildrenState,
} from "../../state/variables";
import { getEntry, useWorkspace, type NotebookEntry } from "../../state/workspace";
import { ResizeHandle } from "../shell/ResizeHandle";
import { ChevronRightIcon, CloseIcon, RefreshIcon } from "../shell/icons";
import styles from "./VariablesPanel.module.css";

const INDENT_PX = 14;

type Row =
  | { kind: "var"; id: string; level: number; path: VariablePathStep[]; name: string; type: string; summary: string; expandable: boolean }
  | { kind: "special"; id: string; count: number }
  | { kind: "more"; id: string; level: number; path: VariablePathStep[]; remaining: number; loading: boolean }
  | { kind: "note"; id: string; level: number; text: string; error?: boolean };

function typeGlyph(type: string): string {
  if (/^(int|float|complex|bool|Decimal)/.test(type)) return "#";
  if (/^(str|bytes|bytearray)/.test(type)) return "a";
  if (/^(list|tuple|set|frozenset|deque|ndarray|Series)/.test(type)) return "[]";
  if (/^(dict|DataFrame|OrderedDict|defaultdict)/.test(type)) return "{}";
  if (/(function|method|class|type|module)/.test(type)) return "ƒ";
  return "•";
}

function childRows(path: VariablePathStep[], level: number, state: Record<string, ChildrenState>, expanded: Record<string, true>, out: Row[]): void {
  const c = state[pathKey(path)];
  if (!c) return;
  for (const child of c.items) addVar(child, [...path, child.key], level, state, expanded, out);
  if (c.error) out.push({ kind: "note", id: `${pathKey(path)}#err`, level, text: c.error, error: true });
  else if (c.loading && c.items.length === 0) out.push({ kind: "note", id: `${pathKey(path)}#load`, level, text: "Loading…" });
  else if (c.items.length < c.total) {
    out.push({ kind: "more", id: `${pathKey(path)}#more`, level, path, remaining: Math.min(CHILDREN_PAGE, c.total - c.items.length), loading: c.loading });
  }
}

function addVar(
  v: VariableItem | VariableChild,
  path: VariablePathStep[],
  level: number,
  state: Record<string, ChildrenState>,
  expanded: Record<string, true>,
  out: Row[],
): void {
  out.push({ kind: "var", id: pathKey(path), level, path, name: v.name, type: v.type, summary: v.summary, expandable: v.expandable });
  if (v.expandable && expanded[pathKey(path)]) childRows(path, level + 1, state, expanded, out);
}

function buildRows(variables: VariableItem[], state: Record<string, ChildrenState>, expanded: Record<string, true>): Row[] {
  const rows: Row[] = [];
  const special = variables.filter((v) => v.group === "special");
  for (const v of variables) if (v.group !== "special") addVar(v, [v.name], 0, state, expanded, rows);
  if (special.length > 0) {
    rows.push({ kind: "special", id: SPECIAL_KEY, count: special.length });
    if (expanded[SPECIAL_KEY]) for (const v of special) addVar(v, [v.name], 1, state, expanded, rows);
  }
  return rows;
}

function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className={styles.empty}>
      <p className={styles.emptyTitle}>{title}</p>
      {hint ? <p>{hint}</p> : null}
    </div>
  );
}

function RowView({ row, expanded }: { row: Row; expanded: Record<string, true> }) {
  const { toggle, toggleSpecial, loadMore } = useVariables.getState();
  const pad = { paddingLeft: `calc(var(--space-3) + ${("level" in row ? row.level : 0) * INDENT_PX}px)` };

  if (row.kind === "note") {
    return (
      <div className={row.error ? `${styles.note} ${styles.noteError}` : styles.note} style={pad} role={row.error ? "alert" : undefined}>
        {row.text}
      </div>
    );
  }
  if (row.kind === "more") {
    return (
      <button type="button" className={styles.more} style={pad} disabled={row.loading} onClick={() => loadMore(row.path)}>
        {row.loading ? "Loading…" : `Show ${row.remaining} more…`}
      </button>
    );
  }
  const isSpecial = row.kind === "special";
  const open = isSpecial ? Boolean(expanded[SPECIAL_KEY]) : Boolean(expanded[row.id]);
  const expandable = isSpecial || row.expandable;
  const act = () => {
    if (isSpecial) toggleSpecial();
    else if (row.expandable) toggle(row.path);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!expandable) return;
    if (e.key === "Enter" || e.key === " " || (e.key === "ArrowRight" && !open) || (e.key === "ArrowLeft" && open)) {
      e.preventDefault();
      act();
    }
  };
  const caret = (
    <span className={styles.caret} data-open={open || undefined} aria-hidden="true">
      {expandable ? <ChevronRightIcon size={12} /> : null}
    </span>
  );
  if (isSpecial) {
    return (
      <div
        className={`${styles.row} ${styles.special}`}
        style={pad}
        role="treeitem"
        aria-level={1}
        aria-expanded={open}
        tabIndex={0}
        data-testid="variables-special"
        onClick={act}
        onKeyDown={onKey}
      >
        {caret}
        <span className={styles.specialLabel}>Special Variables ({row.count})</span>
      </div>
    );
  }
  const full = `${row.name} = {${row.type}} ${row.summary}`;
  return (
    <div
      className={styles.row}
      style={pad}
      role="treeitem"
      aria-level={row.level + 1}
      aria-expanded={row.expandable ? open : undefined}
      tabIndex={0}
      title={full}
      onClick={act}
      onKeyDown={onKey}
    >
      {caret}
      <span className={styles.glyph} aria-hidden="true">{typeGlyph(row.type)}</span>
      <span className={styles.name}>{row.name}</span>
      <span className={styles.type}> = {`{${row.type}}`}</span>
      <span className={styles.summary}> {row.summary}</span>
    </div>
  );
}

const DEAD_HINT = "Run the notebook again to reconnect the kernel.";

function ActiveVariables({ entry }: { entry: NotebookEntry }) {
  const open = useWorkspace((s) => s.rightPanel === "variables");
  const sessionId = useStore(entry.kernel, (s) => s.sessionId);
  const kernelState = useStore(entry.kernel, (s) => s.kernelState);
  const loading = useVariables((s) => s.loading);
  const data = useVariables((s) => s.data);
  const error = useVariables((s) => s.error);
  const expanded = useVariables((s) => s.expanded);
  const children = useVariables((s) => s.children);
  const retries = useVariables((s) => s.retries);
  const live = open && Boolean(sessionId) && (kernelState === "idle" || kernelState === "busy");

  // O store decide quando ler (abertura, transição para idle, debounce, soltar sessão).
  useEffect(() => {
    useVariables.getState().sync({ open, sessionId, kernelState });
  }, [open, sessionId, kernelState]);

  useEffect(() => () => useVariables.getState().sync({ open: false, sessionId: null, kernelState: null }), []);

  const status = data?.status;
  // Kernel idle com `busy`/`stale`: sondagem em voo, não célula rodando; relê com backoff.
  const settling = live && kernelState === "idle" && (status === "busy" || (status === "ok" && data?.stale === true));
  useEffect(() => {
    if (!settling || loading) return;
    return useVariables.getState().scheduleRetry() ?? undefined;
  }, [settling, loading, data]);

  const rows = data && status === "ok" ? buildRows(data.variables, children, expanded) : [];

  let body: ReactNode;
  if (!live) {
    body =
      kernelState === "dead" ? (
        <Empty title="Kernel shut down" hint={DEAD_HINT} />
      ) : kernelState === "restarting" ? (
        <Empty title="Kernel restarting" hint="Variables return after you run a cell." />
      ) : (
        <Empty title="No variables" hint="Run a cell to see variables" />
      );
  } else if (error && !data) {
    body = <p className={`${styles.note} ${styles.noteError}`} role="alert">{error}</p>;
  } else if (!data) {
    body = <p className={styles.note}>Loading…</p>;
  } else if (status === "busy") {
    body =
      kernelState === "idle" && retries < VARIABLES_MAX_RETRIES ? (
        <p className={styles.note}>Reading variables…</p>
      ) : (
        <Empty title="Kernel busy" hint="Variables appear when the cell finishes." />
      );
  } else if (status === "error") {
    body = <p className={`${styles.note} ${styles.noteError}`} role="alert">{data.message ?? "Failed to read the variables."}</p>;
  } else if (status !== "ok") {
    body = <Empty title="Kernel unavailable" hint={DEAD_HINT} />;
  } else if (rows.length === 0) {
    body = <Empty title="No variables" hint="Run a cell to see variables" />;
  } else {
    body = (
      <div role="tree" aria-label="Variables" className={styles.tree}>
        {rows.map((row) => (
          <RowView key={row.id} row={row} expanded={expanded} />
        ))}
        {data.truncated ? (
          <p className={styles.note}>Showing the first {data.variables.length}{data.total ? ` of ${data.total}` : ""} variables.</p>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <header className={styles.header}>
        <h2 className={styles.title}>Variables</h2>
        {data?.executionCount !== undefined && live ? (
          <span className={styles.badge} title="Execution count at the last read">after [{data.executionCount}]</span>
        ) : null}
        <div className={styles.actions}>
          {data?.stale && live ? (
            <span className={styles.stale} role="status" title={kernelState === "idle" ? "Read in progress; showing the last read." : "The kernel is busy; showing the last read."}>
              stale
            </span>
          ) : null}
          <button
            type="button"
            className={styles.iconBtn}
            data-testid="variables-refresh"
            aria-label="Refresh variables"
            title="Refresh"
            disabled={!live || loading}
            onClick={() => useVariables.getState().refresh()}
          >
            <RefreshIcon size={14} />
          </button>
          <CloseButton />
        </div>
      </header>
      <div className={styles.body}>
        <div className={styles.card}>{body}</div>
      </div>
    </>
  );
}

function CloseButton() {
  const setRightPanel = useWorkspace((s) => s.setRightPanel);
  return (
    <button type="button" className={styles.iconBtn} data-testid="variables-close" aria-label="Close variables" title="Close" onClick={() => setRightPanel(null)}>
      <CloseIcon size={14} />
    </button>
  );
}

export function VariablesPanel() {
  const path = useRouter((s) => activeNotebookPath(s.route));
  useWorkspace((s) => s.tabs);
  const entry = path ? getEntry(path) : undefined;
  const width = useLayout((s) => s.variablesWidth);
  const setWidth = useLayout((s) => s.setVariablesWidth);
  const baseWidth = useRef(width);
  return (
    <>
      <ResizeHandle
        orientation="vertical"
        label="Resize variables panel"
        onDragStart={() => {
          baseWidth.current = useLayout.getState().variablesWidth;
        }}
        onDrag={(d) => setWidth(Math.min(baseWidth.current - d, window.innerWidth / 2))}
        onReset={() => setWidth(DEFAULT_VARIABLES_WIDTH)}
      />
      <section className={styles.panel} style={{ width }} aria-label="Variables" data-testid="variables-panel">
        {entry ? (
          <ActiveVariables key={entry.path} entry={entry} />
        ) : (
          <>
            <header className={styles.header}>
              <h2 className={styles.title}>Variables</h2>
              <div className={styles.actions}>
                <CloseButton />
              </div>
            </header>
            <div className={styles.body}>
              <div className={styles.card}>
                <Empty title="No active notebook" hint="Open a notebook to see its variables." />
              </div>
            </div>
          </>
        )}
      </section>
    </>
  );
}
