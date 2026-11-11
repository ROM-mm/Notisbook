import { encodePath, request } from "./http";
import type { CreatedSession, Kernelspec, SessionInfo } from "./types";

export function listKernelspecs(signal?: AbortSignal): Promise<Kernelspec[]> {
  return request<Kernelspec[]>("/api/kernelspecs", { signal });
}

export function listSessions(signal?: AbortSignal): Promise<SessionInfo[]> {
  return request<SessionInfo[]>("/api/sessions", { signal });
}

export function createSession(path: string, kernelName: string): Promise<CreatedSession> {
  return request<CreatedSession>("/api/sessions", {
    method: "POST",
    body: { path, kernel_name: kernelName },
  });
}

export function deleteSession(sessionId: string, opts: { keepalive?: boolean } = {}): Promise<void> {
  return request<void>(`/api/sessions/${encodePath(sessionId)}`, { method: "DELETE", keepalive: opts.keepalive });
}
