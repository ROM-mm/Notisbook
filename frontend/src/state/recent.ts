/**
 * Notebooks abertos recentemente (caminhos relativos à raiz), mais recente
 * primeiro, no máximo `MAX_RECENT`. Persistidos em localStorage como conveniência
 * por navegador, uma lista por raiz de notebooks (`notisbook.recent:<root>`); sem
 * raiz conhecida a lista é vazia e nada é gravado. JSON inválido ou storage
 * indisponível viram lista vazia.
 *
 * Exemplos empacotados (`samplePaths`, informados pelo workspace junto com a raiz via
 * `GET /api/samples`) nunca entram na lista: `touch` os ignora. Ao chegarem, entradas de
 * exemplo já gravadas para a raiz são expurgadas do storage (formato inalterado).
 */
import { create } from "zustand";

const KEY_PREFIX = "notisbook.recent:";
export const MAX_RECENT = 5;

/** Lista gravada da raiz; `null` quando o acesso ao storage falha, `[]` para JSON inválido. */
function readStored(root: string): string[] | null {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(KEY_PREFIX + root);
  } catch {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw ?? "[]");
    if (!Array.isArray(parsed)) return [];
    const paths = parsed.filter((p): p is string => typeof p === "string" && p !== "");
    return [...new Set(paths)].slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

function read(root: string): string[] {
  return readStored(root) ?? [];
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
  /** Caminhos relativos dos exemplos da raiz atual; `touch` não os grava. */
  samplePaths: ReadonlySet<string>;
  /** Informa os exemplos da raiz atual e expurga os já gravados nos recentes dela. */
  setSamplePaths: (paths: readonly string[]) => void;
  /** Troca a raiz e recarrega a lista dela; a mesma raiz é no-op. */
  setRoot: (root: string) => void;
  /** Move `path` para o topo (sem duplicata) e corta em `MAX_RECENT`; exemplo é no-op. */
  touch: (path: string) => void;
  remove: (path: string) => void;
  /** Troca o prefixo `from` por `to` no caminho e nos que estão sob a pasta renomeada. */
  rename: (from: string, to: string) => void;
  /** Remove `path` e tudo sob ele (mesma semântica de `isUnder` do notebookTree). */
  removeUnder: (path: string) => void;
}

export const useRecent = create<RecentState>((set, get) => {
  // Parte do storage para não sobrescrever o que outra aba gravou; sem acesso a ele, da memória.
  const current = (): string[] => {
    const { root, paths } = get();
    return root === null ? paths : (readStored(root) ?? paths);
  };
  const commit = (paths: string[]): void => {
    write(get().root, paths);
    set({ paths });
  };
  return {
    root: null,
    paths: [],
    samplePaths: new Set<string>(),
    setSamplePaths: (paths) => {
      const samplePaths = new Set(paths);
      set({ samplePaths });
      // Parte do storage (regra de sincronia); só grava se havia exemplo ocupando vaga.
      const stored = current();
      const kept = stored.filter((p) => !samplePaths.has(p));
      if (kept.length !== stored.length) commit(kept);
    },
    setRoot: (root) => {
      if (get().root === root) return;
      // Exemplos são por raiz: o workspace relê `GET /api/samples` para a nova.
      set({ root, paths: read(root), samplePaths: new Set<string>() });
    },
    touch: (path) => {
      if (get().samplePaths.has(path)) return;
      commit([path, ...current().filter((p) => p !== path)].slice(0, MAX_RECENT));
    },
    remove: (path) => commit(current().filter((p) => p !== path)),
    rename: (from, to) =>
      commit([...new Set(current().map((p) => (isUnder(p, from) ? `${to}${p.slice(from.length)}` : p)))]),
    removeUnder: (path) => commit(current().filter((p) => !isUnder(p, path))),
  };
});

// Outra aba gravou a lista da raiz atual: adota o valor do storage.
window.addEventListener("storage", (e) => {
  const { root } = useRecent.getState();
  if (root !== null && e.key === KEY_PREFIX + root) useRecent.setState({ paths: read(root) });
});
