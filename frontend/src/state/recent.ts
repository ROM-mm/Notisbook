/**
 * Notebooks abertos recentemente (caminhos relativos à raiz), mais recente
 * primeiro, no máximo `MAX_RECENT`. Persistidos em localStorage como conveniência
 * por navegador, uma lista por raiz de notebooks (`notisbook.recent:<root>`); sem
 * raiz conhecida a lista é vazia e nada é gravado. JSON inválido ou storage
 * indisponível viram lista vazia.
 */
import { create } from "zustand";

const KEY_PREFIX = "notisbook.recent:";
export const MAX_RECENT = 5;

function read(root: string): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(KEY_PREFIX + root) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    const paths = parsed.filter((p): p is string => typeof p === "string" && p !== "");
    return [...new Set(paths)].slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

function isUnder(path: string, base: string): boolean {
  return path === base || path.startsWith(`${base}/`);
}

function write(root: string | null, paths: string[]): void {
  if (root === null) return;
  try {
    window.localStorage.setItem(KEY_PREFIX + root, JSON.stringify(paths));
  } catch {
    /* storage indisponível */
  }
}

interface RecentState {
  /** Caminho da raiz a que `paths` pertence (null até a raiz ser conhecida). */
  root: string | null;
  paths: string[];
  /** Troca a raiz e recarrega a lista dela; a mesma raiz é no-op. */
  setRoot: (root: string) => void;
  /** Move `path` para o topo (sem duplicata) e corta em `MAX_RECENT`. */
  touch: (path: string) => void;
  remove: (path: string) => void;
  /** Troca o prefixo `from` por `to` no caminho e nos que estão sob a pasta renomeada. */
  rename: (from: string, to: string) => void;
  /** Remove `path` e tudo sob ele (mesma semântica de `isUnder` do notebookTree). */
  removeUnder: (path: string) => void;
}

export const useRecent = create<RecentState>((set, get) => ({
  root: null,
  paths: [],
  setRoot: (root) => {
    if (get().root === root) return;
    set({ root, paths: read(root) });
  },
  touch: (path) => {
    const paths = [path, ...get().paths.filter((p) => p !== path)].slice(0, MAX_RECENT);
    write(get().root, paths);
    set({ paths });
  },
  remove: (path) => {
    const paths = get().paths.filter((p) => p !== path);
    write(get().root, paths);
    set({ paths });
  },
  rename: (from, to) => {
    const paths = [
      ...new Set(get().paths.map((p) => (isUnder(p, from) ? `${to}${p.slice(from.length)}` : p))),
    ];
    write(get().root, paths);
    set({ paths });
  },
  removeUnder: (path) => {
    const paths = get().paths.filter((p) => !isUnder(p, path));
    write(get().root, paths);
    set({ paths });
  },
}));
