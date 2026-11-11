import { request } from "./http";

export interface UsedTotal {
  used: number;
  total: number;
}

/** Cada métrica é `null` quando o backend não conseguiu coletá-la. Valores em bytes; `percent` de 0 a 100. */
export interface SystemResources {
  memory: UsedTotal | null;
  cpu: { percent: number; cores: number } | null;
  disk: UsedTotal | null;
}

export function getSystemResources(signal?: AbortSignal): Promise<SystemResources> {
  return request<SystemResources>("/api/system/resources", { signal });
}
