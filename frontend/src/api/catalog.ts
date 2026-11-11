/** Cliente do catálogo persistente (`/api/catalog`), lido do `catalog.db` sem sessão de kernel. */
import { ApiError, errorMessage, request } from "./http";

export interface CatalogTable {
  name: string;
  namespace: string[];
  /** `delta`, `parquet` ou `iceberg`. */
  format: string;
  /** `MANAGED` ou `EXTERNAL`. */
  table_type: string;
  is_temporary: boolean;
  location: string | null;
  /** false quando os arquivos da tabela não existem mais no disco. */
  available: boolean;
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

export interface ColumnsQuery {
  catalog: string;
  database: string;
  table: string;
}

export function getCatalog(signal?: AbortSignal): Promise<CatalogResponse> {
  return request<CatalogResponse>("/api/catalog", { signal });
}

/** 404 tabela inexistente, 409 metadados ilegíveis, 503 `catalog.db` indisponível. */
export function getColumns(q: ColumnsQuery, signal?: AbortSignal): Promise<CatalogColumn[]> {
  return request<CatalogColumn[]>("/api/catalog/columns", {
    query: { catalog: q.catalog, database: q.database, table: q.table },
    signal,
  });
}

/** Regra de nome de schema aceita pelo backend. */
export const SCHEMA_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;

export interface SchemaRef {
  catalog: string;
  name: string;
}

/** 400 `invalid_catalog`/`invalid_name`/`reserved_name`, 409 `schema_exists`, 503 `catalog_busy`/`catalog_unavailable`. */
export function createSchema(catalog: string, name: string): Promise<SchemaRef> {
  return request<SchemaRef>("/api/catalog/schemas", { method: "POST", body: { catalog, name } });
}

export interface SchemaPreview {
  tables: number;
  views: number;
  managed: number;
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
};

/** Código `detail` (string) de um erro de `/api/catalog/schemas`, ou null. */
export function schemaErrorCode(err: unknown): string | null {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : null;
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
