/**
 * Estado da seção Files: raiz escolhida (persistida em localStorage), nós
 * expandidos e listagens carregadas sob demanda, uma por diretório.
 */
import { create } from "zustand";
import { listPath, type FsEntry } from "../api/files";
import { errorMessage } from "../api/http";

const ROOT_KEY = "notisbook.files.root";

export interface DirState {
  entries: FsEntry[];
  nextOffset: number | null;
  loading: boolean;
  error: string | null;
}

function readRoot(): string | null {
  try {
    const v = window.localStorage.getItem(ROOT_KEY);
    return v && v.startsWith("/") ? v : null;
  } catch {
    return null;
  }
}

function writeRoot(root: string | null): void {
  try {
    if (root) window.localStorage.setItem(ROOT_KEY, root);
    else window.localStorage.removeItem(ROOT_KEY);
  } catch {
    /* storage indisponível */
  }
}

interface FilesState {
  root: string | null;
  expanded: Record<string, true>;
  dirs: Record<string, DirState>;
  setRoot: (path: string | null) => void;
  toggle: (path: string) => void;
  expand: (path: string) => void;
  collapse: (path: string) => void;
  loadMore: (path: string) => void;
  /** Lista a raiz restaurada do localStorage; chamar só após a autenticação. */
  loadRoot: () => void;
  /** Recarrega a raiz e todos os diretórios expandidos. */
  refresh: () => void;
  /** Recarrega a listagem de `dir`, mantendo a anterior visível. */
  reload: (dir: string) => void;
  /** Esquece expansão e listagem de `path` e de tudo sob ele (pasta excluída). */
  forget: (path: string) => void;
}

function isUnder(path: string, base: string): boolean {
  return path === base || path.startsWith(base.endsWith("/") ? base : `${base}/`);
}

function omitUnder<T>(record: Record<string, T>, base: string): Record<string, T> {
  return Object.fromEntries(Object.entries(record).filter(([key]) => !isUnder(key, base)));
}

/** Invalida respostas em voo quando a raiz muda ou a árvore é recarregada. */
let generation = 0;
const PAGE = 200;

export const useFiles = create<FilesState>((set, get) => {
  async function load(path: string, offset: number): Promise<void> {
    const gen = generation;
    const prev = get().dirs[path];
    set((s) => ({
      dirs: {
        ...s.dirs,
        [path]: { entries: offset > 0 ? (prev?.entries ?? []) : [], nextOffset: null, loading: true, error: null },
      },
    }));
    try {
      const res = await listPath(path, offset, PAGE);
      if (gen !== generation) return;
      set((s) => ({
        dirs: {
          ...s.dirs,
          [path]: {
            entries: offset > 0 ? [...(s.dirs[path]?.entries ?? []), ...res.entries] : res.entries,
            nextOffset: res.truncated ? res.next_offset : null,
            loading: false,
            error: null,
          },
        },
      }));
    } catch (err) {
      if (gen !== generation) return;
      set((s) => ({
        dirs: {
          ...s.dirs,
          [path]: { entries: s.dirs[path]?.entries ?? [], nextOffset: null, loading: false, error: errorMessage(err) },
        },
      }));
    }
  }

  function expand(path: string): void {
    set((s) => ({ expanded: { ...s.expanded, [path]: true } }));
    const d = get().dirs[path];
    if (!d || d.error) void load(path, 0);
  }

  return {
    root: readRoot(),
    expanded: {},
    dirs: {},
    setRoot: (path) => {
      generation += 1;
      writeRoot(path);
      set({ root: path, expanded: {}, dirs: {} });
      if (path) void load(path, 0);
    },
    toggle: (path) => {
      if (get().expanded[path]) get().collapse(path);
      else expand(path);
    },
    expand,
    collapse: (path) =>
      set((s) => {
        const { [path]: _removed, ...rest } = s.expanded;
        return { expanded: rest };
      }),
    loadMore: (path) => {
      const d = get().dirs[path];
      if (d && !d.loading && d.nextOffset !== null) void load(path, d.nextOffset);
    },
    loadRoot: () => {
      const { root } = get();
      if (root) void load(root, 0);
    },
    refresh: () => {
      const { root, expanded } = get();
      if (!root) return;
      generation += 1;
      set({ dirs: {} });
      void load(root, 0);
      for (const p of Object.keys(expanded)) void load(p, 0);
    },
    reload: (dir) => void load(dir, 0),
    forget: (path) => {
      set((s) => ({ expanded: omitUnder(s.expanded, path), dirs: omitUnder(s.dirs, path) }));
    },
  };
});
