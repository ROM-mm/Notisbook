import { ApiError, request } from "./http";

/** Espelha `backend/src/notisbook/api/notislake.py` (prefixo `/api/notislake`). */
const BASE = "/api/notislake";

export type NotislakeMode = "automatic" | "manual" | "invalid";
export type NotislakeSource = "local" | "manual";
export type NotislakeLocalState = "stopped" | "starting" | "running" | "restarting" | "failed" | "stopping";

export interface NotislakeLocal {
  state: NotislakeLocalState;
  since: string;
  restarts: number;
  api_port: number | null;
  console_port: number | null;
  console_url: string | null;
  error: { code: string; message: string } | null;
}

/** `local` é `null` quando o app sobe sem supervisor do MinIO. */
export interface NotislakeStatus {
  mode: NotislakeMode;
  local: NotislakeLocal | null;
}

/** Conexão do MinIO local exibida no modo automático; nunca inclui a secret key. */
export interface NotislakeLocalConnection {
  endpoint: string;
  access_key: string;
  region: string;
}

/** `mode=invalid` traz só o campo inconsistente; `automatic` traz o MinIO local (`null` se parado). */
export type NotislakeConfig =
  | { mode: "automatic"; local: NotislakeLocalConnection | null }
  | { mode: "invalid"; field: string | null }
  | {
      mode: "manual";
      name: string;
      endpoint: string;
      access_key: string;
      region: string;
      timeout_s: number;
      has_secret: boolean;
    };

/** Rascunho enviado no PUT/test. `secret_key` vazio ou ausente reaproveita o segredo salvo (422 `secret_required` se endpoint/access_key mudaram). */
export interface NotislakeConfigDraft {
  name: string;
  endpoint: string;
  access_key: string;
  secret_key?: string;
  region?: string;
  timeout_s?: number;
}

export interface NotislakeObject {
  key: string;
  size: number;
  last_modified: string | null;
}

export interface NotislakeObjectPage {
  source: NotislakeSource;
  bucket: string;
  prefix: string;
  prefixes: string[];
  objects: NotislakeObject[];
  is_truncated: boolean;
  next_continuation_token: string | null;
}

export type NotislakeTestResult =
  | { ok: true; source: NotislakeSource }
  | { ok: false; source: NotislakeSource; code: string; message: string };

export interface NotislakeObjectsQuery {
  /** Sem `bucket` vale o contrato antigo (bucket `notislake`). */
  bucket?: string;
  prefix?: string;
  maxKeys?: number;
  continuationToken?: string | null;
}

export function getNotislakeStatus(signal?: AbortSignal): Promise<NotislakeStatus> {
  return request<NotislakeStatus>(`${BASE}/status`, { signal });
}

/** 202 com o estado; 409 `not_failed` se o MinIO local não está em falha. */
export function retryNotislake(): Promise<{ state: NotislakeLocalState }> {
  return request<{ state: NotislakeLocalState }>(`${BASE}/retry`, { method: "POST" });
}

/** Credencial do MinIO local, sob demanda e só para cópia; 409 `not_running` fora de `running`. Nunca guardar nem logar. */
export function getNotislakeLocalCredentials(): Promise<{ user: string; password: string }> {
  return request<{ user: string; password: string }>(`${BASE}/local/credentials`);
}

export function getNotislakeConfig(signal?: AbortSignal): Promise<NotislakeConfig> {
  return request<NotislakeConfig>(`${BASE}/config`, { signal });
}

/** O segredo trafega só neste corpo; a resposta expõe apenas `has_secret`. 422 por campo. */
export function putNotislakeConfig(draft: NotislakeConfigDraft): Promise<NotislakeConfig> {
  return request<NotislakeConfig>(`${BASE}/config`, { method: "PUT", body: draft });
}

/** 204: volta ao modo automático. */
export function deleteNotislakeConfig(): Promise<void> {
  return request<void>(`${BASE}/config`, { method: "DELETE" });
}

/** Lista um nível por prefixo (`prefixes` = pastas); 503 `notislake_unavailable`, 409 `config_invalid`, 502/504/400 do destino. */
export function listNotislakeObjects(
  { bucket, prefix, maxKeys, continuationToken }: NotislakeObjectsQuery = {},
  signal?: AbortSignal,
): Promise<NotislakeObjectPage> {
  return request<NotislakeObjectPage>(`${BASE}/objects`, {
    signal,
    query: {
      bucket: bucket || undefined,
      prefix: prefix || undefined,
      max_keys: maxKeys === undefined ? undefined : String(maxKeys),
      continuation_token: continuationToken ?? undefined,
    },
  });
}

/** Sem rascunho sonda a conexão vigente. Falha do destino volta 200 com `ok: false` e `code`; 409 `test_in_progress`. */
export function testNotislakeConnection(draft?: NotislakeConfigDraft, signal?: AbortSignal): Promise<NotislakeTestResult> {
  return request<NotislakeTestResult>(`${BASE}/test`, { method: "POST", body: draft, signal });
}

export interface NotislakeBucketList {
  source: NotislakeSource;
  /** No modo manual a lista é sintética: só `notislake`. */
  buckets: string[];
}

/** Códigos `detail.code` das rotas de buckets e exclusão. */
export type NotislakeManageErrorCode =
  | "bucket_exists"
  | "bucket_missing"
  | "bucket_not_empty"
  | "content_changed"
  | "delete_in_progress"
  | "manual_mode_unsupported"
  | "notislake_unavailable";

/** Retorno das exclusões: quantidade de objetos removidos (`0` em arquivo que já não existia). */
export interface NotislakeDeleted {
  deleted: number;
}

export function listNotislakeBuckets(signal?: AbortSignal): Promise<NotislakeBucketList> {
  return request<NotislakeBucketList>(`${BASE}/buckets`, { signal });
}

/** 201 com o nome; cria `landing/ bronze/ silver/ gold/`. 422 nome inválido; 409 `bucket_exists` ou `manual_mode_unsupported`. */
export function createNotislakeBucket(name: string): Promise<{ name: string }> {
  return request<{ name: string }>(`${BASE}/buckets`, { method: "POST", body: { name } });
}

/** Objetos sob o prefixo (vazio = bucket inteiro); base do `expected_count` das exclusões. 404 `bucket_missing`. */
export function getNotislakeSummary(bucket: string, prefix = "", signal?: AbortSignal): Promise<{ object_count: number }> {
  return request<{ object_count: number }>(`${BASE}/buckets/${encodeURIComponent(bucket)}/summary`, {
    signal,
    query: { prefix: prefix || undefined },
  });
}

/** Exclui todos os objetos e o bucket. 409 `content_changed` (com `object_count`), `bucket_not_empty`, `delete_in_progress`. */
export function deleteNotislakeBucket(bucket: string, expectedCount: number): Promise<NotislakeDeleted> {
  return request<NotislakeDeleted>(`${BASE}/buckets/${encodeURIComponent(bucket)}`, {
    method: "DELETE",
    query: { expected_count: String(expectedCount) },
  });
}

/** `prefix` termina em `/`. 409 `content_changed` (com `object_count`) ou `delete_in_progress`. */
export function deleteNotislakeFolder(bucket: string, prefix: string, expectedCount: number): Promise<NotislakeDeleted> {
  return request<NotislakeDeleted>(`${BASE}/folders`, {
    method: "DELETE",
    query: { bucket, prefix, expected_count: String(expectedCount) },
  });
}

export function deleteNotislakeObject(bucket: string, key: string): Promise<NotislakeDeleted> {
  return request<NotislakeDeleted>(`${BASE}/objects`, { method: "DELETE", query: { bucket, key } });
}

/** Contagem atual devolvida no 409 `content_changed`; `null` para qualquer outro erro. */
export function contentChangedCount(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409 || err.code !== "content_changed") return null;
  const count = (err.detail as { object_count?: unknown }).object_count;
  return typeof count === "number" ? count : null;
}
