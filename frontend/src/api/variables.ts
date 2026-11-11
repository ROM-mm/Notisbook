/** Cliente das variáveis do kernel (`/api/sessions/{id}/variables`). */
import { request } from "./http";
import type { VariableChildrenResponse, VariablePathStep, VariablesResponse } from "./types";

const base = (sessionId: string) => `/api/sessions/${encodeURIComponent(sessionId)}/variables`;

export function getVariables(sessionId: string, signal?: AbortSignal): Promise<VariablesResponse> {
  return request<VariablesResponse>(base(sessionId), { signal });
}

/** Filhos de `path` (nome da variável + chaves); o caminho vai como lista JSON. */
export function getVariableChildren(
  sessionId: string,
  path: VariablePathStep[],
  offset: number,
  limit: number,
  signal?: AbortSignal,
): Promise<VariableChildrenResponse> {
  return request<VariableChildrenResponse>(`${base(sessionId)}/children`, {
    query: { path: JSON.stringify(path), offset: String(offset), limit: String(limit) },
    signal,
  });
}
