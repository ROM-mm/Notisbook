/** Utilitários de caminhos relativos ("a/b/c.ipynb"). */

export function joinPath(dir: string, name: string): string {
  return dir ? `${dir.replace(/\/+$/, "")}/${name}` : name;
}

export function dirname(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}

export function basename(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? path : path.slice(i + 1);
}

export interface Crumb {
  name: string;
  path: string;
}

/** "a/b/c" → [{a,"a"}, {b,"a/b"}, {c,"a/b/c"}]. */
export function crumbs(path: string): Crumb[] {
  const parts = path.split("/").filter(Boolean);
  return parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join("/") }));
}

/** Nome válido para uma entrada (sem barra, sem ser oculto/"..", não vazio). */
export function validateName(name: string): string | null {
  const n = name.trim();
  if (!n) return "Enter a name.";
  if (n.includes("/")) return "The name cannot contain “/”.";
  if (n.startsWith(".")) return "The name cannot start with “.”.";
  return null;
}

export const NOTEBOOK_EXT = ".ipynb";

/** Primeiro nome livre: "Sem título.ipynb", "Sem título 1.ipynb", ... */
export function uniqueName(taken: Iterable<string>, stem: string, ext: string): string {
  const set = new Set(taken);
  for (let i = 0; ; i += 1) {
    const candidate = `${i === 0 ? stem : `${stem} ${i}`}${ext}`;
    if (!set.has(candidate)) return candidate;
  }
}

/** Nome exibido de um notebook: basename sem `.ipynb`. */
export function notebookTitle(path: string): string {
  const name = basename(path);
  return name.toLowerCase().endsWith(NOTEBOOK_EXT) ? name.slice(0, -NOTEBOOK_EXT.length) : name;
}
