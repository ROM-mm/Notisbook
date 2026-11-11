/**
 * Núcleo HTTP: caminhos relativos `/api/...` (mesma origem em produção,
 * proxy do Vite em dev), autenticação por cookie/Bearer e erros `{detail}`.
 */

/** Códigos de `detail` da raiz dos notebooks → texto para o usuário (o `detail` bruto segue em `ApiError.detail`). */
const CODE_MESSAGES: Record<string, string> = {
  locked: "The notebooks folder was fixed with --root and cannot be changed here.",
  sessions_active: "Close the notebooks with a running kernel (in any window) before changing the folder.",
  root_changed: "The notebooks folder changed in another window. Reload the page.",
};

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(ApiError.describe(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** FastAPI devolve `detail` como string ou lista de erros de validação. */
  static describe(status: number, detail: unknown): string {
    if (typeof detail === "string") return CODE_MESSAGES[detail] ?? detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
        .filter((m): m is string => m !== null);
      if (msgs.length > 0) return msgs.join("; ");
    }
    return `HTTP ${status}`;
  }
}

/** Token mantido só em memória (nunca em storage). O cookie HttpOnly é a credencial principal. */
let memoryToken: string | null = null;

export function setAuthToken(token: string | null): void {
  memoryToken = token;
}

/** Geração da raiz dos notebooks conhecida por esta aba; enviada em todo request (null = ainda desconhecida). */
let rootGeneration: number | null = null;

export function setRootGeneration(generation: number | null): void {
  rootGeneration = generation;
}

export function getRootGeneration(): number | null {
  return rootGeneration;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | undefined>;
  signal?: AbortSignal;
  /** Mantém a requisição viva ao fechar/navegar a página (ex.: DELETE da sessão). */
  keepalive?: boolean;
}

export function buildUrl(path: string, query?: Record<string, string | undefined>): string {
  const params = new URLSearchParams();
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) params.set(k, v);
    }
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Codifica um caminho relativo segmento a segmento (preserva as barras). */
export function encodePath(path: string): string {
  return path
    .split("/")
    .filter((s) => s.length > 0)
    .map(encodeURIComponent)
    .join("/");
}

/** Cabeçalhos comuns: autenticação em memória e geração da raiz. */
function commonHeaders(accept: string): Record<string, string> {
  const headers: Record<string, string> = { Accept: accept };
  if (memoryToken) headers.Authorization = `Bearer ${memoryToken}`;
  if (rootGeneration !== null) headers["X-Notisbook-Root-Generation"] = String(rootGeneration);
  return headers;
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail: unknown = null;
  try {
    const data: unknown = await res.json();
    detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
  } catch {
    detail = res.statusText || null;
  }
  return new ApiError(res.status, detail);
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = commonHeaders("application/json");
  let body: string | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method ?? "GET",
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
    keepalive: opts.keepalive,
  });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Nome do arquivo em `Content-Disposition`, preferindo `filename*` (RFC 6266/5987). */
function dispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent((star[1] ?? "").trim());
    } catch {
      /* cai para filename= */
    }
  }
  const plain = /filename\s*=\s*"([^"]*)"/i.exec(header) ?? /filename\s*=\s*([^;]+)/i.exec(header);
  return plain?.[1] ? plain[1].trim() : null;
}

/** Como `request`, mas devolve o corpo binário (download) e o nome sugerido pelo servidor. */
export async function requestBlob(
  path: string,
  opts: RequestOptions = {},
): Promise<{ blob: Blob; filename: string | null }> {
  const headers = commonHeaders("*/*");
  let body: string | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method ?? "GET",
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
  });
  if (!res.ok) throw await toApiError(res);
  return { blob: await res.blob(), filename: dispositionFilename(res.headers.get("Content-Disposition")) };
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
