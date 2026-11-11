import { encodePath, request } from "./http";
import type { Job, JobAccepted, PackageList, Prereqs, RequirementRow, SparkCatalog, SparkVersions } from "./types";

export function getPrereqs(signal?: AbortSignal): Promise<Prereqs> {
  return request<Prereqs>("/api/system/prereqs", { signal });
}

export function getSparkCatalog(signal?: AbortSignal): Promise<SparkCatalog> {
  return request<SparkCatalog>("/api/spark/catalog", { signal });
}

export function getSparkVersions(signal?: AbortSignal): Promise<SparkVersions> {
  return request<SparkVersions>("/api/spark/versions", { signal });
}

/** 202 com `job_id`; 422 versão inválida, 409 instalação em andamento. */
export function installSparkVersion(version: string): Promise<JobAccepted> {
  return request<JobAccepted>("/api/spark/versions", { method: "POST", body: { version } });
}

/** 204; 404 não instalada, 409 em uso/instalando, 422 inválida. */
export function removeSparkVersion(version: string): Promise<void> {
  return request<void>(`/api/spark/versions/${encodePath(version)}`, { method: "DELETE" });
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/api/jobs/${encodePath(jobId)}`, { signal });
}

const packagesPath = (version: string) => `/api/spark/versions/${encodePath(version)}/packages`;

/** 404 não instalada, 503 sem uv, 500 falha ao listar. */
export function listPackages(version: string, signal?: AbortSignal): Promise<PackageList> {
  return request<PackageList>(packagesPath(version), { signal });
}

/** 202 com `job_id`; 422 (lista de `{loc, msg}` por linha), 409 sessão aberta/job em andamento. */
export function addPackages(version: string, requirements: RequirementRow[]): Promise<JobAccepted> {
  return request<JobAccepted>(packagesPath(version), { method: "POST", body: { requirements } });
}

/** Leva cada lib à última versão. 202; 422/409 como em `addPackages`. */
export function upgradePackages(version: string, names: string[]): Promise<JobAccepted> {
  return request<JobAccepted>(`${packagesPath(version)}/upgrade`, { method: "POST", body: { names } });
}

/** Desinstala as libs numa só chamada. 202; 422/409 como em `addPackages`. */
export function uninstallPackages(version: string, names: string[]): Promise<JobAccepted> {
  return request<JobAccepted>(`${packagesPath(version)}/uninstall`, { method: "POST", body: { names } });
}
