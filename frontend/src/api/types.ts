/** Tipos dos contratos REST do backend Notisbook. */

export type CellLanguage = "python" | "sql" | "duckdb";

export type ContentType = "dir" | "notebook" | "file";

export interface ContentEntry {
  name: string;
  /** Caminho relativo à raiz servida pelo backend. */
  path: string;
  type: ContentType;
  /** Epoch em segundos (float). */
  mtime: number;
  size: number | null;
}

export type CreateKind = "notebook" | "directory";

export interface Kernelspec {
  name: string;
  display_name: string;
  language: string;
  /** Linguagens de célula que o kernel executa, em ordem canônica; ausente em backends antigos. */
  cell_languages?: CellLanguage[];
}

export type KernelState = "starting" | "idle" | "busy" | "restarting" | "dead";

export interface SessionInfo {
  session_id: string;
  path: string;
  kernel_name: string;
  state: KernelState;
}

export interface CreatedSession {
  session_id: string;
}

export interface JdkInfo {
  version: string;
  home: string;
}

export interface Prereqs {
  uv: { found: boolean; version: string | null };
  java: {
    version: string | null;
    ok: boolean;
    jdks: JdkInfo[];
    spark3_ok: boolean;
    spark4_ok: boolean;
  };
  java_home: string | null;
}

export interface CatalogVersion {
  version: string;
  released_at: string | null;
  installed: boolean;
}

export interface SparkCatalog {
  source: "pypi" | "fallback";
  fallback: boolean;
  versions: CatalogVersion[];
}

export interface InstalledSpark {
  version: string;
  kernel_name: string;
  display_name: string;
  legacy: boolean;
  env_dir: string | null;
  /** `installed`, `outdated` (env anterior à matriz atual), `missing` ou `unsupported`. */
  bundle_status?: string;
}

export interface InstallingSpark {
  kernel_name: string;
  job_id: string;
  /** "install" (instalação da versão) ou "packages" (mudança de libs do ambiente). */
  kind: "install" | "packages";
}

export interface SparkVersions {
  installed: InstalledSpark[];
  catalog: CatalogVersion[];
  installing: InstallingSpark[];
}

export interface InstalledDuckDB {
  version: string;
  kernel_name: string;
  display_name: string;
  env_dir: string;
  extension_directory: string;
  extensions: string[];
}

export interface DuckDBStatus {
  kernel_name: string;
  supported: boolean;
  /** Versão fixada no manifesto; `null` se o manifesto não carregou. */
  version: string | null;
  installed: InstalledDuckDB | null;
  installing: { job_id: string; kind: string } | null;
}

export interface DuckDBExtension {
  name: string;
  installed: boolean;
}

export interface DuckDBExtensions {
  version: string;
  extensions: DuckDBExtension[];
}

export interface PackageItem {
  name: string;
  version: string;
}

export interface PackageList {
  version: string;
  kernel_name: string;
  env_dir: string;
  /** Job de instalação/libs em andamento neste ambiente. */
  job_id: string | null;
  /** Ação do job de libs em andamento; null se não há job de libs. */
  job_action: "add" | "upgrade" | "uninstall" | null;
  packages: PackageItem[];
}

export interface RequirementRow {
  name: string;
  /** Especificador PEP 440 (`>=2.0,<3`); vazio = última versão. */
  spec: string;
}

export interface JobAccepted {
  job_id: string;
}

export type JobState = "queued" | "running" | "succeeded" | "failed";

export interface JobLogLine {
  phase: string;
  line: string;
  progress?: number;
}

export interface Job {
  id: string;
  kind: string;
  version: string;
  state: JobState;
  error: string | null;
  log: JobLogLine[];
}

/** Prefixo do `kernel_name` dos runtimes Docker em `/api/kernelspecs` e `/api/sessions`. */
export const DOCKER_KERNEL_PREFIX = "notisbook-docker-";

export interface DockerfileInfo {
  /** Caminho relativo ao repositório do Notisbook. */
  path: string;
  text: string;
  base_image: string | null;
  base_digest: string | null;
}

export interface DockerMounts {
  registered: string[];
  /** Pastas que uma recriação montaria agora; null se não foi possível planejar. */
  current: string[] | null;
  /** O container montado difere das pastas atuais (ex.: Connections trocada). */
  stale: boolean;
  missing: string[];
  extra: string[];
  error: string | null;
}

export interface DockerContainer {
  status: string;
  running: boolean;
  owned: boolean;
}

/** Versões lidas na validação da instalação (chaves ausentes quando não relatadas). */
export type DockerVersions = Partial<Record<"python" | "spark" | "pyspark" | "java" | "sqlite3" | "spark_session", string>>;

export interface DockerRuntime {
  key: string;
  label: string;
  kernel_name: string;
  formats: string[];
  image: string;
  container_name: string;
  dockerfile: DockerfileInfo;
  available: boolean;
  installed: boolean;
  busy: boolean;
  job: { id: string; kind: "install" | "recreate" } | null;
  image_present: boolean | null;
  image_size: number | null;
  container: DockerContainer | null;
  mounts: DockerMounts | null;
  versions: DockerVersions;
}

export interface DockerRuntimes {
  available: boolean;
  runtimes: DockerRuntime[];
}

export interface DockerRuntimeDetails extends DockerRuntime {
  python: string | null;
  packages: PackageItem[];
}
