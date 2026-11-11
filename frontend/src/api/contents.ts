import { encodePath, request } from "./http";
import type { Notebook } from "./nbformat";
import type { ContentEntry, CreateKind } from "./types";

/** Lista um diretório (raiz quando `path` é vazio). */
export function listDir(path = "", signal?: AbortSignal): Promise<ContentEntry[]> {
  return request<ContentEntry[]>("/api/contents", { query: { path: path || undefined }, signal });
}

export function getNotebook(path: string, signal?: AbortSignal): Promise<Notebook> {
  return request<Notebook>(`/api/contents/${encodePath(path)}`, { signal });
}

/** Salva o notebook inteiro (nbformat v4). */
export function saveNotebook(path: string, notebook: Notebook): Promise<ContentEntry> {
  return request<ContentEntry>(`/api/contents/${encodePath(path)}`, { method: "PUT", body: notebook });
}

/** Cria notebook vazio ou diretório (201). */
export function createEntry(path: string, type: CreateKind): Promise<ContentEntry> {
  return request<ContentEntry>(`/api/contents/${encodePath(path)}`, { method: "POST", body: { type } });
}

export function renameEntry(path: string, newPath: string): Promise<ContentEntry> {
  return request<ContentEntry>(`/api/contents/${encodePath(path)}`, {
    method: "PATCH",
    body: { new_path: newPath },
  });
}

/** Remove notebook ou pasta (recursivo); 204 sem corpo. */
export function deleteEntry(path: string): Promise<void> {
  return request<void>(`/api/contents/${encodePath(path)}`, { method: "DELETE" });
}
