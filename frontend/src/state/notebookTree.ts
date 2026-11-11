/**
 * Árvore do painel Notebooks: pastas expandidas, listagem por pasta (cache só em memória)
 * e item selecionado. Cada pasta é carregada só ao expandir.
 *
 * `generation` sobe a cada `reset` (troca da pasta raiz): respostas em voo da geração
 * anterior são descartadas em vez de repovoar a árvore com a raiz antiga.
 */
import { create } from "zustand";
import { errorMessage, listDir, type ContentEntry } from "../api";
import { crumbs, dirname } from "../lib/paths";

export type DirStatus = "loading" | "ready" | "error";

export interface DirState {
  /** Listagem completa (inclui arquivos comuns, que a árvore esconde mas `uniqueName` precisa ver). */
  entries: ContentEntry[];
  status: DirStatus;
  error: string | null;
}

export interface TreeSelection {
  path: string;
  type: ContentEntry["type"];
}

const ORDER: Record<ContentEntry["type"], number> = { dir: 0, notebook: 1, file: 2 };

function sortEntries(entries: ContentEntry[]): ContentEntry[] {
  return [...entries].sort(
    (a, b) => ORDER[a.type] - ORDER[b.type] || a.name.localeCompare(b.name, "en-US", { sensitivity: "base" }),
  );
}

function isUnder(path: string, base: string): boolean {
  return path === base || path.startsWith(`${base}/`);
}

function omitUnder<T>(record: Record<string, T>, base: string): Record<string, T> {
  return Object.fromEntries(Object.entries(record).filter(([key]) => !isUnder(key, base)));
}

/** Última requisição por pasta: só a mais recente grava o resultado. */
const latest = new Map<string, number>();
let seq = 0;

interface TreeState {
  expanded: Record<string, true>;
  dirs: Record<string, DirState>;
  generation: number;
  selected: TreeSelection | null;

  /** Carrega `dir` (mantém a listagem anterior visível durante a recarga). */
  reload: (dir: string) => Promise<void>;
  /** Carrega a raiz se ainda não houver listagem. */
  ensureRoot: () => void;
  expand: (dir: string) => void;
  collapse: (dir: string) => void;
  toggle: (dir: string) => void;
  /** Recarrega a raiz e as pastas expandidas; descarta as demais para refazer o fetch ao expandir. */
  reloadAll: () => void;
  /** Expande `dir` e cada ancestral (recarrega cada um; a listagem anterior segue visível). */
  expandTo: (dir: string) => void;
  /** Esquece expansão, listagem e seleção de `path` e de tudo sob ele (renomeado/excluído). */
  forget: (path: string) => void;
  select: (selection: TreeSelection | null) => void;
  /** Zera a árvore (troca de raiz) e invalida respostas em voo. */
  reset: () => void;
}

export const useNotebookTree = create<TreeState>((set, get) => ({
  expanded: {},
  dirs: {},
  generation: 0,
  selected: null,

  reload: async (dir) => {
    const { generation } = get();
    const ticket = ++seq;
    latest.set(dir, ticket);
    set((s) => ({
      dirs: { ...s.dirs, [dir]: { entries: s.dirs[dir]?.entries ?? [], status: "loading", error: null } },
    }));
    try {
      const entries = sortEntries(await listDir(dir));
      if (get().generation !== generation || latest.get(dir) !== ticket) return;
      set((s) => {
        const sel = s.selected;
        const gone = sel !== null && dirname(sel.path) === dir && !entries.some((e) => e.path === sel.path);
        return { dirs: { ...s.dirs, [dir]: { entries, status: "ready", error: null } }, selected: gone ? null : sel };
      });
    } catch (err) {
      if (get().generation !== generation || latest.get(dir) !== ticket) return;
      set((s) => ({ dirs: { ...s.dirs, [dir]: { entries: s.dirs[dir]?.entries ?? [], status: "error", error: errorMessage(err) } } }));
    }
  },

  ensureRoot: () => {
    if (!get().dirs[""]) void get().reload("");
  },

  expand: (dir) => {
    set((s) => ({ expanded: { ...s.expanded, [dir]: true } }));
    const state = get().dirs[dir];
    // Já carregada: revalida em background (o reload mantém as entradas visíveis).
    if (!state || state.status === "error" || state.status === "ready") void get().reload(dir);
  },

  collapse: (dir) =>
    set((s) => {
      const { [dir]: _closed, ...rest } = s.expanded;
      return { expanded: rest };
    }),

  toggle: (dir) => (get().expanded[dir] ? get().collapse(dir) : get().expand(dir)),

  reloadAll: () => {
    const { reload, expanded } = get();
    set((s) => ({
      dirs: Object.fromEntries(Object.entries(s.dirs).filter(([key]) => key === "" || s.expanded[key])),
    }));
    void reload("");
    for (const dir of Object.keys(expanded)) void reload(dir);
  },

  expandTo: (dir) => {
    get().ensureRoot();
    for (const c of crumbs(dir)) get().expand(c.path);
  },

  forget: (path) => {
    // Invalida reloads em voo sob `path`: sem ticket vigente eles não regravam `dirs`.
    for (const key of [...latest.keys()]) if (isUnder(key, path)) latest.delete(key);
    set((s) => ({
      expanded: omitUnder(s.expanded, path),
      dirs: omitUnder(s.dirs, path),
      selected: s.selected && isUnder(s.selected.path, path) ? null : s.selected,
    }));
  },

  select: (selected) => set({ selected }),

  reset: () => {
    latest.clear();
    set((s) => ({ expanded: {}, dirs: {}, selected: null, generation: s.generation + 1 }));
  },
}));

/**
 * Pasta onde New folder / New notebook criam: a selecionada; para um notebook
 * selecionado, a pasta dele; sem seleção, a raiz ("").
 */
export function targetDirOf(selected: TreeSelection | null): string {
  if (selected === null) return "";
  if (selected.type === "dir") return selected.path;
  return dirname(selected.path);
}

export const selectTargetDir = (s: { selected: TreeSelection | null }): string => targetDirOf(s.selected);

export function getTargetDir(): string {
  return targetDirOf(useNotebookTree.getState().selected);
}
