import { encodePath, request } from "./http";
import type { DuckDBExtensions, DuckDBStatus, JobAccepted, PackageList, RequirementRow } from "./types";

/** Catálogo curado, versões instaladas e jobs em andamento (instalação e libs). */
export function getDuckDBStatus(signal?: AbortSignal): Promise<DuckDBStatus> {
  return request<DuckDBStatus>("/api/duckdb", { signal });
}

const versionPath = (version: string) => `/api/duckdb/versions/${encodePath(version)}`;

/** Nome do kernelspec de uma versão (`2.0.1` → `duckdb-2-0-1`), como no backend. */
export const duckdbKernelName = (version: string) => `duckdb-${version.replace(/\./g, "-")}`;

/** 202 com `job_id`; 422 versão fora do catálogo/plataforma sem suporte, 409 sessão ativa ou job em andamento. */
export function installDuckDBVersion(version: string): Promise<JobAccepted> {
  return request<JobAccepted>("/api/duckdb/versions", { method: "POST", body: { version } });
}

/** 204; 404 não instalada, 409 sessão ativa ou job em andamento, 500 remoção incompleta. */
export function removeDuckDBVersion(version: string): Promise<void> {
  return request<void>(versionPath(version), { method: "DELETE" });
}

/** Extensões do manifesto da versão e se cada uma está instalada. */
export function getDuckDBExtensions(version: string, signal?: AbortSignal): Promise<DuckDBExtensions> {
  return request<DuckDBExtensions>(`${versionPath(version)}/extensions`, { signal });
}

const packagesPath = (version: string) => `${versionPath(version)}/packages`;

/** Libs do ambiente (sem `duckdb`/`ipykernel`). 404 não instalada, 503 sem uv. Mesmo contrato do Spark. */
export function listDuckDBPackages(version: string, signal?: AbortSignal): Promise<PackageList> {
  return request<PackageList>(packagesPath(version), { signal });
}

/** 202 com `job_id`; 422 (lista de `{loc, msg}` por linha, inclui `duckdb` protegido), 409 sessão aberta/job em andamento. */
export function addDuckDBPackages(version: string, requirements: RequirementRow[]): Promise<JobAccepted> {
  return request<JobAccepted>(packagesPath(version), { method: "POST", body: { requirements } });
}

/** Leva cada lib à última versão. 202; 422/409 como em `addDuckDBPackages`. */
export function upgradeDuckDBPackages(version: string, names: string[]): Promise<JobAccepted> {
  return request<JobAccepted>(`${packagesPath(version)}/upgrade`, { method: "POST", body: { names } });
}

/** Desinstala as libs numa só chamada. 202; 422/409 como em `addDuckDBPackages`. */
export function uninstallDuckDBPackages(version: string, names: string[]): Promise<JobAccepted> {
  return request<JobAccepted>(`${packagesPath(version)}/uninstall`, { method: "POST", body: { names } });
}
