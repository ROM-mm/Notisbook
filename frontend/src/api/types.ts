/** Tipos dos contratos REST do backend Notisbook. */

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

/** Variável do kernel; `group: "special"` agrupa dunders/internos no fim da lista. */
export interface VariableItem {
  name: string;
  type: string;
  summary: string;
  expandable: boolean;
  group: "user" | "special";
}

/** `ok`, `busy`, `error` ou `kernel_<estado>`; `busy` + `stale` + lista vazia = sem cache. */
export interface VariablesResponse {
  status: string;
  stale: boolean;
  variables: VariableItem[];
  executionCount?: number;
  total?: number;
  truncated?: boolean;
  message?: string;
}

/** Passo do caminho de um filho: o primeiro é o nome da variável; os demais, `key` (str ou int). */
export type VariablePathStep = string | number;

export interface VariableChild {
  key: VariablePathStep;
  name: string;
  type: string;
  summary: string;
  expandable: boolean;
}

/** `ok`, `stale_path`, `busy`, `error` ou `kernel_<estado>`. */
export interface VariableChildrenResponse {
  status: string;
  stale: boolean;
  children: VariableChild[];
  total: number;
  offset: number;
  message?: string;
}
