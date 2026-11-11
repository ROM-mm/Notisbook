import { request, setRootGeneration } from "./http";

export interface NotebooksRoot {
  path: string;
  name: string;
  source: "cli" | "saved" | "default";
  /** `--root` explícito: a troca pela UI é recusada. */
  locked: boolean;
  generation: number;
}

export function getNotebooksRoot(signal?: AbortSignal): Promise<NotebooksRoot> {
  return request<NotebooksRoot>("/api/notebooks-root", { signal });
}

/** Troca a raiz e adota a nova geração (as próximas escritas já a enviam). */
export async function putNotebooksRoot(path: string): Promise<NotebooksRoot> {
  const root = await request<NotebooksRoot>("/api/notebooks-root", { method: "PUT", body: { path } });
  setRootGeneration(root.generation);
  return root;
}

/** Valida o caminho como raiz sem checar sessões, persistir nem trocar (`dry_run`); não mexe na geração. */
export function validateNotebooksRoot(path: string): Promise<{ path: string; name: string }> {
  return request<{ path: string; name: string }>("/api/notebooks-root", {
    method: "PUT",
    body: { path },
    query: { dry_run: "true" },
  });
}
