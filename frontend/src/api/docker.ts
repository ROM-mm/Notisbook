import { encodePath, request } from "./http";
import type { DockerRuntimeDetails, DockerRuntimes, JobAccepted } from "./types";

const runtimePath = (key: string) => `/api/docker/runtimes/${encodePath(key)}`;

/** A pasta Connections vive no navegador: vai em toda leitura para o backend apontar a defasagem das montagens. */
const connectionsQuery = (connectionsDir: string | null) => ({ connections_dir: connectionsDir ?? undefined });

export function listDockerRuntimes(connectionsDir: string | null, signal?: AbortSignal): Promise<DockerRuntimes> {
  return request<DockerRuntimes>("/api/docker/runtimes", { query: connectionsQuery(connectionsDir), signal });
}

export function getDockerDetails(key: string, connectionsDir: string | null, signal?: AbortSignal): Promise<DockerRuntimeDetails> {
  return request<DockerRuntimeDetails>(`${runtimePath(key)}/details`, { query: connectionsQuery(connectionsDir), signal });
}

/** 202 com `job_id`; 422 por campo (`connections_dir`, `notebooks_root`, `warehouse`), 409 em alteração/sessão aberta, 404 runtime desconhecido. */
export function installDockerRuntime(key: string, connectionsDir: string | null, recreate: boolean): Promise<JobAccepted> {
  return request<JobAccepted>(`${runtimePath(key)}/install`, {
    method: "POST",
    body: { connections_dir: connectionsDir, recreate },
  });
}

/** 204; 409/404/503/500 com `detail`. */
export function stopDockerRuntime(key: string): Promise<void> {
  return request<void>(`${runtimePath(key)}/stop`, { method: "POST" });
}

export function restartDockerRuntime(key: string): Promise<void> {
  return request<void>(`${runtimePath(key)}/restart`, { method: "POST" });
}

/** Apaga o container e o registro do kernel; a imagem é mantida. */
export function removeDockerRuntime(key: string): Promise<void> {
  return request<void>(runtimePath(key), { method: "DELETE" });
}
