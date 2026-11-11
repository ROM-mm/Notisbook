import { ApiError, errorMessage, request } from "./http";

export interface FsPlace {
  label: string;
  path: string;
}

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  is_symlink: boolean;
  size: number | null;
  mtime: number | null;
}

export interface FsListing {
  path: string;
  parent: string | null;
  entries: FsEntry[];
  total: number;
  truncated: boolean;
  next_offset: number | null;
}

/** Atalhos de diretório (Home, Notebooks, Root). */
export function getPlaces(signal?: AbortSignal): Promise<FsPlace[]> {
  return request<FsPlace[]>("/api/fs/places", { signal });
}

/** Lista um nível do diretório absoluto `path`, paginado. */
export function listPath(path: string, offset = 0, limit = 200, signal?: AbortSignal): Promise<FsListing> {
  return request<FsListing>("/api/fs/list", {
    query: { path, offset: String(offset), limit: String(limit) },
    signal,
  });
}

export interface ChooseDirResult {
  path?: string;
  cancelled?: boolean;
}

/** Abre o "Escolher pasta" nativo do macOS no servidor; bloqueia até o usuário decidir. */
export function chooseDirectory(
  defaultPath?: string | null,
  signal?: AbortSignal,
  purpose: "data" | "notebooks" = "data",
): Promise<ChooseDirResult> {
  return request<ChooseDirResult>("/api/fs/choose-dir", {
    method: "POST",
    body: { purpose, ...(defaultPath ? { default_path: defaultPath } : {}) },
    signal,
  });
}

/** Remove a pasta `path` (ou só o link, se for symlink). 204; erros com `detail` objeto `{code, message, ...}`. */
export function deleteDir(path: string, signal?: AbortSignal): Promise<void> {
  return request<void>("/api/fs/dir", { method: "DELETE", query: { path }, signal });
}

const MAX_TABLES_SHOWN = 5;

/** `detail.message` do erro de `deleteDir`; em `contains_catalog_tables` cita as tabelas afetadas. */
export function deleteDirMessage(err: unknown): string {
  const d = err instanceof ApiError ? err.detail : null;
  if (!d || typeof d !== "object" || !("message" in d) || typeof d.message !== "string") return errorMessage(err);
  let text = d.message;
  if ("code" in d && d.code === "contains_catalog_tables" && "tables" in d && Array.isArray(d.tables)) {
    const names = d.tables.map(String);
    const total = "table_count" in d && typeof d.table_count === "number" ? d.table_count : names.length;
    const shown = names.slice(0, MAX_TABLES_SHOWN);
    const more = total - shown.length;
    text += ` Tables: ${shown.join(", ")}${more > 0 ? ` and ${more} more` : ""}.`;
  }
  return text;
}
