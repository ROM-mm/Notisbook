/** Cliente do catálogo persistente (`/api/catalog`), lido do `catalog.db` sem sessão de kernel. */
import { ApiError, errorMessage, request } from "./http";

export interface CatalogTable {
  name: string;
  namespace: string[];
  /** `delta`, `parquet`, `hudi` ou `iceberg`; no `glue` também `csv`, `json`, `orc`, `avro` ou `unknown`. */
  format: string;
  /** `MANAGED` ou `EXTERNAL`. */
  table_type: string;
  is_temporary: boolean;
  location: string | null;
  /** false quando os arquivos não existem mais no disco; null quando não verificável (ex.: s3a). */
  available: boolean | null;
  description: string | null;
}

export interface CatalogDatabase {
  name: string;
  tables: CatalogTable[];
  truncated?: boolean;
}

export interface CatalogNode {
  name: string;
  databases: CatalogDatabase[];
  /** Código de falha da leitura deste catálogo (os demais seguem válidos). */
  error?: string;
}

export interface CatalogResponse {
  status: string;
  catalogs: CatalogNode[];
}

export interface CatalogColumn {
  name: string;
  data_type: string;
  nullable: boolean;
  is_partition: boolean;
  is_bucket?: boolean;
  description: string | null;
}

export interface TableQuery {
  catalog: string;
  database: string;
  table: string;
}

export function getCatalog(signal?: AbortSignal): Promise<CatalogResponse> {
  return request<CatalogResponse>("/api/catalog", { signal });
}

export type TableFormat = "delta" | "parquet" | "hudi" | "iceberg" | "csv" | "json" | "orc" | "avro" | "unknown";
/**
 * Semântica do DROP decidida pelo backend, igual em todos os catálogos: `deletes_files` (gerenciada na própria pasta;
 * os arquivos entram na fila de exclusão executada pelo kernel), `registry_only` (externa; os arquivos ficam),
 * `keeps_files_outside_managed` (gerenciada fora da própria pasta reservada; o DROP remove só o registro) ou
 * `keeps_files_shared` (gerenciada cuja pasta é usada por outra tabela; o DROP mantém os arquivos).
 */
export type DropBehavior = "deletes_files" | "registry_only" | "keeps_files_outside_managed" | "keeps_files_shared";
/**
 * Origem de `columns` numa tabela do `glue`: `storage_descriptor` (Columns do Glue), `spark_properties`
 * (schema gravado pelo Spark nos parâmetros) ou `delta_log` (schema no `_delta_log`; `columns` traz só as partições).
 */
export type SchemaSource = "storage_descriptor" | "spark_properties" | "delta_log";
export type TableMetadataError = "unavailable" | "store_unavailable";

export interface TableVersion {
  kind: "delta_version" | "hudi_instant" | "iceberg_snapshot" | "glue_version";
  value: string | number | null;
}

/** Snapshot Iceberg; ids são texto (long de 64 bits perderia precisão como number). */
export interface TableHistoryEntry {
  id: string | null;
  timestamp_ms: number | null;
  operation: string | null;
  parent_id: string | null;
  summary: Record<string, string>;
}

export interface TableStats {
  total_records: number | null;
  total_files_size: number | null;
  total_data_files: number | null;
}

/** Armazenamento de uma tabela do `glue` (StorageDescriptor e parâmetros do AWS Glue). */
export interface GlueStorage {
  classification: string | null;
  input_format: string | null;
  output_format: string | null;
  serde_library: string | null;
  compressed: boolean | null;
  /** `TableType` do Glue (`EXTERNAL_TABLE` ou `MANAGED_TABLE`). */
  glue_table_type: string | null;
}

/** Metadados de uma tabela sem kernel; `history`/`stats` só existem no Iceberg, `properties` no Iceberg e no `glue`. */
export interface TableInfo {
  catalog: string;
  database: string;
  table: string;
  format: TableFormat;
  table_type: "MANAGED" | "EXTERNAL";
  drop_behavior: DropBehavior;
  location: string | null;
  available: boolean | null;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
  partition_columns: string[];
  columns: CatalogColumn[];
  version: TableVersion | null;
  history: TableHistoryEntry[] | null;
  properties: Record<string, string> | null;
  stats: TableStats | null;
  metadata_error: TableMetadataError | null;
  /** Só no catálogo `glue`. */
  schema_source?: SchemaSource | null;
  /** Só no catálogo `glue`. */
  glue?: GlueStorage | null;
}

/** 404 tabela inexistente, 409 schema Iceberg não suportado, 503 `catalog.db` indisponível. */
export function getTableInfo(q: TableQuery, signal?: AbortSignal): Promise<TableInfo> {
  return request<TableInfo>("/api/catalog/table", {
    query: { catalog: q.catalog, database: q.database, table: q.table },
    signal,
  });
}

/** `session` = spark_catalog, `named` = iceberg. */
export type CatalogKind = "session" | "named";
export type CatalogInfoStatus = "ok" | "empty" | "unsupported_iceberg_catalog_schema" | "iceberg_catalog_unreadable";

export interface CatalogConfigEntry {
  key: string;
  /** Já mascarado no backend quando `redacted`. */
  value: string;
  redacted: boolean;
}

export interface CatalogNamespaceSummary {
  name: string;
  tables: number;
  views: number;
}

/** Painel Catalog info: contagens do `catalog.db` e a config do perfil Spark local (sem kernel). */
export interface CatalogInfo {
  name: string;
  kind: CatalogKind;
  backing_catalog: string | null;
  status: CatalogInfoStatus;
  profile: string;
  implementation: string | null;
  type: string | null;
  warehouse: string | null;
  uri: string | null;
  file_io: string | null;
  counts: { namespaces: number; tables: number; views: number };
  formats: Record<string, number>;
  namespaces: CatalogNamespaceSummary[];
  namespaces_truncated: boolean;
  config: CatalogConfigEntry[];
}

/** 404 catálogo desconhecido, 503 `catalog.db` indisponível. */
export function getCatalogInfo(catalog: string, signal?: AbortSignal): Promise<CatalogInfo> {
  return request<CatalogInfo>("/api/catalog/info", { query: { catalog }, signal });
}

/** Regra de nome de schema aceita pelo backend. */
export const SCHEMA_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;

export interface SchemaRef {
  catalog: string;
  name: string;
}

/**
 * 400 `invalid_catalog`/`invalid_name`/`reserved_name`, 409 `schema_exists`/`namespace_case_collision`,
 * 503 `catalog_busy`/`catalog_unavailable`.
 */
export function createSchema(catalog: string, name: string): Promise<SchemaRef> {
  return request<SchemaRef>("/api/catalog/schemas", { method: "POST", body: { catalog, name } });
}

export interface SchemaPreview {
  /** Total de tabelas do schema, de todos os formatos (Delta/Parquet/Hudi no `spark_catalog`, Iceberg no `iceberg`). */
  tables: number;
  views: number;
  /** Sempre 0: o backend não apaga pastas de tabelas gerenciadas. */
  managed: number;
  /** Gerenciadas no bucket reservado cujas pastas entram na fila de exclusão (o kernel as apaga). */
  managed_queued: number;
  /** Só a MANAGED legada com location local: a pasta permanece após a exclusão do schema. */
  managed_kept: number;
  external: number;
  can_delete: boolean;
  /** Código do motivo quando `can_delete` é false. */
  reason: string | null;
  /** Estado lido; a exclusão só vale se o catálogo ainda corresponder a ele. */
  etag: string;
}

/** 404 `schema_not_found`. */
export function previewSchemaDeletion(catalog: string, schema: string, signal?: AbortSignal): Promise<SchemaPreview> {
  return request<SchemaPreview>("/api/catalog/schemas/preview", { query: { catalog, schema }, signal });
}

export interface SchemaDeletion {
  dropped_tables: number;
  dropped_views: number;
  files_deleted: string[];
  /** Tabelas cujas pastas entraram na fila de exclusão (o kernel as apaga). */
  files_queued: string[];
  files_kept: { table: string; reason: string }[];
  folder_kept: boolean;
}

/** 409 `catalog_changed`/`cannot_drop_default`/`has_child_namespaces`/`kernel_busy`, 404, 503. */
export function deleteSchema(catalog: string, schema: string, etag: string): Promise<SchemaDeletion> {
  return request<SchemaDeletion>("/api/catalog/schemas", { method: "DELETE", query: { catalog, schema, etag } });
}

const SCHEMA_ERRORS: Record<string, string> = {
  invalid_name: "Use letters, digits and underscores, starting with a letter or underscore (max 128).",
  reserved_name: "This name is reserved.",
  schema_exists: "A schema with this name already exists.",
  unsupported_iceberg_catalog_schema: "Iceberg catalog schema is not supported.",
  catalog_busy: "The catalog is busy. Try again.",
  catalog_unavailable: "Catalog database unavailable. Try again.",
  schema_not_found: "The schema no longer exists.",
  cannot_drop_default: "The default schema cannot be deleted.",
  has_child_namespaces: "The schema has nested namespaces and cannot be deleted.",
  kernel_busy: "A kernel is using the catalog. Try again when it is idle.",
  catalog_changed: "The schema changed. Review and confirm again.",
  namespace_case_collision: "A schema whose name differs only in letter case already exists.",
};

/** Código `detail` (string) de um erro de `/api/catalog`, ou null. */
function detailCode(err: unknown): string | null {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : null;
}

/** Código `detail` (string) de um erro de `/api/catalog/schemas`, ou null. */
export function schemaErrorCode(err: unknown): string | null {
  return detailCode(err);
}

/** Mensagem curta em inglês para o código do backend; sem mapeamento, o texto do erro. */
export function schemaErrorMessage(err: unknown): string {
  const code = schemaErrorCode(err);
  return (code && SCHEMA_ERRORS[code]) || errorMessage(err);
}

/** Texto para o `reason` de um preview que não pode ser excluído. */
export function schemaReasonMessage(reason: string | null): string {
  return (reason && SCHEMA_ERRORS[reason]) || "This schema cannot be deleted.";
}

/** Efeito da remoção pelo painel: só a entrada do catálogo sai; os arquivos ficam. */
export type RemoveEffect = "registry_only";
/** `managed_use_drop`: gerenciada na própria pasta; só o DROP TABLE (sessão) apaga a tabela e os arquivos. */
export type TableRemovalReason = "managed_use_drop";

/** Prévia da remoção de uma tabela do `spark_catalog` só do registro. */
export interface TableRemovalPreview {
  catalog: string;
  /** Nomes como estão gravados (a busca no backend não distingue caixa). */
  database: string;
  table: string;
  table_type: "MANAGED" | "EXTERNAL";
  location: string | null;
  remove_effect: RemoveEffect;
  can_remove: boolean;
  /** Código do motivo quando `can_remove` é false. */
  reason: TableRemovalReason | null;
  /** Estado lido; a remoção só vale se a linha ainda corresponder a ele. */
  etag: string;
}

/** 400 `invalid_catalog`/`invalid_name`, 404 `table_not_found`, 503 `catalog_busy`/`catalog_unavailable`. */
export function previewTableRemoval(q: TableQuery, signal?: AbortSignal): Promise<TableRemovalPreview> {
  return request<TableRemovalPreview>("/api/catalog/tables/preview", {
    query: { catalog: q.catalog, database: q.database, table: q.table },
    signal,
  });
}

export interface TableRemoval {
  removed: TableQuery;
  /** Sempre vazios: a remoção não apaga nem enfileira arquivos. */
  files_deleted: string[];
  files_queued: string[];
  generation: number;
}

/** 409 `catalog_changed`/`managed_use_drop`, 404 `table_not_found`, 400, 503. */
export function removeTable(q: TableQuery, etag: string): Promise<TableRemoval> {
  return request<TableRemoval>("/api/catalog/tables", {
    method: "DELETE",
    query: { catalog: q.catalog, database: q.database, table: q.table, etag },
  });
}

const TABLE_ERRORS: Record<string, string> = {
  invalid_catalog: "Only spark_catalog tables can be removed from the catalog here.",
  invalid_name: "Invalid schema or table name.",
  table_not_found: "The table no longer exists.",
  catalog_changed: "The table changed. Review and confirm again.",
  managed_use_drop: "Managed table in its own folder: use DROP TABLE in a session to delete the table and its files.",
  catalog_busy: "The catalog is busy. Try again.",
  catalog_unavailable: "Catalog database unavailable. Try again.",
};

/** Código `detail` (string) de um erro de `/api/catalog/tables`, ou null. */
export function tableErrorCode(err: unknown): string | null {
  return detailCode(err);
}

/** Mensagem curta em inglês para o código do backend; sem mapeamento, o texto do erro. */
export function tableErrorMessage(err: unknown): string {
  const code = tableErrorCode(err);
  return (code && TABLE_ERRORS[code]) || errorMessage(err);
}

/** Texto para o `reason` de uma prévia que não pode ser removida. */
export function tableReasonMessage(reason: string | null): string {
  return (reason && TABLE_ERRORS[reason]) || "This table cannot be removed from the catalog.";
}
