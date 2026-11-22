import { request } from "./http";
import type { DuckDBExtensions, DuckDBStatus, JobAccepted } from "./types";

export function getDuckDBStatus(signal?: AbortSignal): Promise<DuckDBStatus> {
  return request<DuckDBStatus>("/api/duckdb", { signal });
}

/** Extensões do manifesto e se cada uma está instalada. */
export function getDuckDBExtensions(signal?: AbortSignal): Promise<DuckDBExtensions> {
  return request<DuckDBExtensions>("/api/duckdb/extensions", { signal });
}

/** 202 com `job_id`; 422 plataforma sem suporte, 409 sessão ativa ou outro job em andamento. */
export function installDuckDB(): Promise<JobAccepted> {
  return request<JobAccepted>("/api/duckdb/install", { method: "POST" });
}

/** 204; 404 não instalado, 409 sessão ativa ou job em andamento, 500 remoção incompleta. */
export function removeDuckDB(): Promise<void> {
  return request<void>("/api/duckdb", { method: "DELETE" });
}
