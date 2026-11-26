/**
 * Estado do painel Notislake (MinIO/S3): status da conexão com polling, lista
 * de buckets (cada um é uma raiz da árvore) e listagens por prefixo sob demanda.
 * Os nós são indexados por `<bucket>/<prefixo>` (raiz do bucket = `<bucket>/`). O polling usa setTimeout encadeado (nunca
 * sobrepõe leituras), é contado por consumidor (`start`/`stop`) e pausa com a
 * aba oculta. O store não recebe nem guarda credenciais: o diálogo de
 * configuração chama a API direto.
 */
import { create } from "zustand";
import { ApiError, errorMessage } from "../api/http";
import {
  createNotislakeBucket,
  deleteNotislakeBucket,
  deleteNotislakeFolder,
  deleteNotislakeObject,
  getNotislakeStatus,
  getNotislakeSummary,
  listNotislakeBuckets,
  listNotislakeObjects,
  retryNotislake,
  type NotislakeObject,
  type NotislakeStatus,
} from "../api/notislake";

const FAST_INTERVAL_MS = 3_000;
const SLOW_INTERVAL_MS = 30_000;
const BACKOFF_AFTER_FAILURES = 3;
const PAGE_SIZE = 200;

export interface NotislakeDirState {
  prefixes: string[];
  objects: NotislakeObject[];
  nextToken: string | null;
  loading: boolean;
  error: string | null;
}

interface NotislakeState {
  status: NotislakeStatus | null;
  statusError: string | null;
  retrying: boolean;
  retryError: string | null;
  /** Raízes da árvore; `null` antes da primeira listagem (ou após troca de conexão). */
  buckets: string[] | null;
  bucketsLoading: boolean;
  bucketsError: string | null;
  /** Nós abertos, por `nodeKey`; fechar remove o nó e todos os descendentes. */
  expanded: Record<string, true>;
  /** Listagens por `nodeKey`; só existem para nós abertos (fechar descarta). */
  dirs: Record<string, NotislakeDirState>;
  start: () => void;
  stop: () => void;
  /** Com `force`, aborta a leitura em andamento e reemite; sem ele, é ignorado se já houver uma. */
  refreshStatus: (force?: boolean) => void;
  /** Descarta árvore e cache (nova conexão): invalida listagens em voo e zera buckets/expansão. */
  reset: () => void;
  retry: () => void;
  toggle: (key: string) => void;
  /** Abre o nó e SEMPRE recarrega a listagem (ação manual). */
  expand: (key: string) => void;
  /** Fecha o nó e descarta a listagem dele e das subpastas carregadas. */
  collapse: (key: string) => void;
  /** Carrega a lista de buckets se ainda não houver (nem carga em andamento). */
  ensureBuckets: () => void;
  /** Recarrega a lista de buckets (ação manual); buckets que sumiram saem da árvore. */
  loadBuckets: () => Promise<void>;
  loadMore: (key: string) => void;
  /** Sem argumento recarrega status, lista de buckets e as pastas abertas; com chave, só ela. */
  refresh: (key?: string) => void;
  /** Recarga no idle do kernel: em silêncio, buckets e nós abertos, sem encolher o que já foi paginado; ação manual prevalece. */
  refreshExpanded: () => void;
  /** Cria o bucket (com landing/bronze/silver/gold), recarrega a lista e abre o bucket. Rejeita com `ApiError`. */
  createBucket: (name: string) => Promise<void>;
  /** Quantidade de objetos sob o prefixo (vazio = bucket inteiro); base do `expected_count`. */
  summary: (bucket: string, prefix?: string) => Promise<number>;
  /** Exclui o bucket inteiro. 409 `content_changed` ⇒ reconfirmar com `contentChangedCount(err)`. Devolve os removidos. */
  deleteBucket: (bucket: string, expectedCount: number) => Promise<number>;
  /** Exclui a pasta (`prefix` termina em `/`) e recarrega a pasta-mãe. Mesmo 409 de `deleteBucket`. */
  deleteFolder: (bucket: string, prefix: string, expectedCount: number) => Promise<number>;
  /** Exclui um arquivo e recarrega a pasta-mãe; `0` se ele já não existia. */
  deleteObject: (bucket: string, key: string) => Promise<number>;
}

/** Bucket aberto automaticamente na primeira listagem de buckets. */
const DEFAULT_BUCKET = "notislake";

const EMPTY_TREE = { buckets: null, bucketsLoading: false, bucketsError: null, expanded: {}, dirs: {} } as const;

/** Chave do nó: `<bucket>/<prefixo>`; a raiz do bucket é `<bucket>/`. */
export function nodeKey(bucket: string, prefix = ""): string {
  return `${bucket}/${prefix}`;
}

/** Inverso de `nodeKey` (nome de bucket nunca contém `/`). */
export function splitNodeKey(key: string): { bucket: string; prefix: string } {
  const i = key.indexOf("/");
  return i < 0 ? { bucket: key, prefix: "" } : { bucket: key.slice(0, i), prefix: key.slice(i + 1) };
}

/** Chave da pasta que contém o nó (`b/a/c/` ou `b/a/x.csv` → `b/a/`; filho direto do bucket → `b/`). */
function parentKey(key: string): string {
  const { bucket, prefix } = splitNodeKey(key);
  const trimmed = prefix.endsWith("/") ? prefix.slice(0, -1) : prefix;
  const cut = trimmed.lastIndexOf("/");
  return nodeKey(bucket, cut < 0 ? "" : trimmed.slice(0, cut + 1));
}

/** Criar/excluir só no MinIO local (modo automático em `running`); no manual a API devolve 409. */
export function isNotislakeManageable(status: NotislakeStatus | null): boolean {
  return status?.mode === "automatic" && status.local?.state === "running";
}

/** A árvore só é consultável com conexão manual ou com o MinIO local em `running`. */
export function isNotislakeTreeAvailable(status: NotislakeStatus | null): boolean {
  if (!status) return false;
  if (status.mode === "manual") return true;
  return status.mode === "automatic" && status.local?.state === "running";
}

/** Chave que muda quando as listagens em cache deixam de valer. */
function sourceKey(status: NotislakeStatus): string {
  return `${status.mode}:${isNotislakeTreeAvailable(status)}`;
}

/** Ativo enquanto houver ao menos um consumidor. */
let consumers = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let statusController: AbortController | null = null;
let inFlight = false;
let failures = 0;
/** Invalida listagens em voo quando o cache é descartado. */
let generation = 0;
let lastKey: string | null = null;

/** Verdadeiro se todo ancestral do nó (`b/`, `b/a/`) está expandido; a raiz do bucket (`b/`) é sempre visível. */
function ancestorsExpanded(key: string, expanded: Record<string, true>): boolean {
  const parts = key.split("/").filter(Boolean);
  for (let i = 1; i < parts.length; i += 1) {
    if (!expanded[`${parts.slice(0, i).join("/")}/`]) return false;
  }
  return true;
}

function clearTimer(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
}

function nextDelay(status: NotislakeStatus | null): number {
  if (failures >= BACKOFF_AFTER_FAILURES) return SLOW_INTERVAL_MS;
  // Só o MinIO local gerenciado muda de estado sozinho; os demais casos são estáveis.
  const transient = status?.mode === "automatic" && status.local !== null && status.local.state !== "running";
  return transient || status === null ? FAST_INTERVAL_MS : SLOW_INTERVAL_MS;
}

function schedule(): void {
  clearTimer();
  if (consumers === 0 || document.hidden) return;
  timer = setTimeout(() => void pollStatus(), nextDelay(useNotislake.getState().status));
}

async function fetchStatus(): Promise<void> {
  if (consumers === 0 || inFlight) return;
  inFlight = true;
  const controller = new AbortController();
  statusController = controller;
  try {
    const status = await getNotislakeStatus(controller.signal);
    if (controller.signal.aborted || consumers === 0) return;
    failures = 0;
    const key = sourceKey(status);
    if (lastKey !== null && key !== lastKey) {
      generation += 1;
      useNotislake.setState({ status, statusError: null, ...EMPTY_TREE });
    } else {
      useNotislake.setState({ status, statusError: null });
    }
    lastKey = key;
  } catch (err) {
    // Leitura abortada (stop/start rápido ou refetch forçado) não é falha do backend.
    if (controller.signal.aborted || consumers === 0) return;
    failures += 1;
    useNotislake.setState({ statusError: errorMessage(err) });
  } finally {
    // Uma leitura abortada não pode zerar o estado da que a substituiu.
    if (statusController === controller) {
      inFlight = false;
      statusController = null;
    }
  }
}

async function pollStatus(): Promise<void> {
  await fetchStatus();
  schedule();
}

function onVisibility(): void {
  if (consumers === 0) return;
  clearTimer();
  if (!document.hidden && !inFlight) void pollStatus();
}

export const useNotislake = create<NotislakeState>((set, get) => {
  /** Nós em recarga silenciosa; evitam duas recargas simultâneas do mesmo nó. */
  const silent = new Set<string>();
  /** Nós que pediram recarga durante uma em andamento; rodam uma vez ao fim dela. */
  const pending = new Set<string>();
  /**
   * Contador de ações manuais por nó: a recarga silenciosa descarta o resultado se ele mudou,
   * e uma listagem manual descarta o seu se o nó foi fechado/reaberto no meio.
   */
  const manualStamp = new Map<string, number>();
  /** Idem para a lista de buckets. */
  let bucketsStamp = 0;
  let bucketsSilent = false;

  function bump(key: string): number {
    const next = (manualStamp.get(key) ?? 0) + 1;
    manualStamp.set(key, next);
    return next;
  }

  /** Remove o nó e os descendentes de `expanded`/`dirs`, invalidando listagens em voo deles. */
  function dropSubtree(key: string): void {
    const { dirs, expanded } = get();
    const inside = (k: string) => k.startsWith(key);
    for (const k of Object.keys(dirs)) if (inside(k)) bump(k);
    const nextDirs = Object.fromEntries(Object.entries(dirs).filter(([k]) => !inside(k)));
    const nextExpanded = Object.fromEntries(Object.entries(expanded).filter(([k]) => !inside(k))) as Record<string, true>;
    set({ dirs: nextDirs, expanded: nextExpanded });
  }

  /** Aplica uma nova lista de buckets e tira da árvore os que sumiram. */
  function applyBuckets(buckets: string[]): void {
    const first = get().buckets === null;
    const known = new Set(buckets);
    const gone = new Set<string>();
    for (const k of [...Object.keys(get().dirs), ...Object.keys(get().expanded)]) {
      const { bucket } = splitNodeKey(k);
      if (!known.has(bucket)) gone.add(bucket);
    }
    for (const bucket of gone) dropSubtree(nodeKey(bucket));
    set({ buckets, bucketsLoading: false, bucketsError: null });
    if (first && Object.keys(get().expanded).length === 0 && known.has(DEFAULT_BUCKET)) {
      expand(nodeKey(DEFAULT_BUCKET));
    }
  }

  async function loadBuckets(): Promise<void> {
    const gen = generation;
    const stamp = ++bucketsStamp;
    set({ bucketsLoading: true, bucketsError: null });
    try {
      const { buckets } = await listNotislakeBuckets();
      if (gen !== generation || stamp !== bucketsStamp) return;
      applyBuckets(buckets);
    } catch (err) {
      if (gen !== generation || stamp !== bucketsStamp) return;
      set({ bucketsLoading: false, bucketsError: errorMessage(err) });
    }
  }

  async function reloadBucketsSilently(): Promise<void> {
    if (bucketsSilent || get().buckets === null || get().bucketsLoading) return;
    bucketsSilent = true;
    const gen = generation;
    const stamp = bucketsStamp;
    try {
      const { buckets } = await listNotislakeBuckets();
      if (gen !== generation || stamp !== bucketsStamp) return;
      applyBuckets(buckets);
    } catch {
      // Falha na recarga automática mantém a lista atual; o Refresh manual segue disponível.
    } finally {
      bucketsSilent = false;
    }
  }

  async function load(key: string, token: string | null, replace: boolean): Promise<void> {
    const gen = generation;
    const prev = get().dirs[key];
    if (prev?.loading) return;
    const stamp = bump(key);
    const stale = () => gen !== generation || manualStamp.get(key) !== stamp;
    const { bucket, prefix } = splitNodeKey(key);
    set((s) => ({
      dirs: {
        ...s.dirs,
        [key]: {
          prefixes: prev?.prefixes ?? [],
          objects: prev?.objects ?? [],
          nextToken: prev?.nextToken ?? null,
          loading: true,
          error: null,
        },
      },
    }));
    try {
      const page = await listNotislakeObjects({ bucket, prefix, maxKeys: PAGE_SIZE, continuationToken: token });
      if (stale()) return;
      set((s) => {
        const base = replace ? undefined : s.dirs[key];
        const prefixes = [...(base?.prefixes ?? []), ...page.prefixes];
        const objects = [...(base?.objects ?? []), ...page.objects];
        return {
          dirs: {
            ...s.dirs,
            [key]: {
              prefixes: [...new Set(prefixes)],
              objects,
              nextToken: page.is_truncated ? page.next_continuation_token : null,
              loading: false,
              error: null,
            },
          },
        };
      });
    } catch (err) {
      if (stale()) return;
      set((s) => {
        const cur = s.dirs[key];
        return {
          dirs: {
            ...s.dirs,
            [key]: {
              prefixes: cur?.prefixes ?? [],
              objects: cur?.objects ?? [],
              nextToken: cur?.nextToken ?? null,
              loading: false,
              error: errorMessage(err),
            },
          },
        };
      });
      // Bucket excluído por fora: a lista de buckets tira o nó da árvore.
      if (err instanceof ApiError && err.code === "bucket_missing") void loadBuckets();
    }
  }

  async function reloadSilently(key: string): Promise<void> {
    const gen = generation;
    const prev = get().dirs[key];
    if (!prev || prev.loading || prev.error) return;
    if (silent.has(key)) {
      pending.add(key);
      return;
    }
    silent.add(key);
    const stamp = manualStamp.get(key) ?? 0;
    const stale = () => gen !== generation || (manualStamp.get(key) ?? 0) !== stamp;
    const target = prev.prefixes.length + prev.objects.length;
    const { bucket, prefix } = splitNodeKey(key);
    try {
      const prefixes: string[] = [];
      const objects: NotislakeObject[] = [];
      let token: string | null = null;
      let truncated = false;
      do {
        const page = await listNotislakeObjects({ bucket, prefix, maxKeys: PAGE_SIZE, continuationToken: token });
        if (stale()) return;
        prefixes.push(...page.prefixes);
        objects.push(...page.objects);
        truncated = page.is_truncated;
        token = truncated ? page.next_continuation_token : null;
      } while (truncated && token !== null && new Set(prefixes).size + objects.length < target);
      if (stale()) return;
      set((s) => ({
        dirs: {
          ...s.dirs,
          [key]: { prefixes: [...new Set(prefixes)], objects, nextToken: token, loading: false, error: null },
        },
      }));
    } catch {
      // Falha na recarga automática mantém a listagem atual; o Retry manual segue disponível.
    } finally {
      silent.delete(key);
      if (pending.delete(key)) void reloadSilently(key);
    }
  }

  function expand(key: string): void {
    set((s) => ({ expanded: { ...s.expanded, [key]: true } }));
    // Abrir é ação manual: sempre relista (dado gravado por notebook aparece ao reabrir).
    void load(key, null, true);
  }

  function collapse(key: string): void {
    dropSubtree(key);
  }

  /** Recarrega a pasta-mãe do nó, se estiver aberta. */
  function reloadParent(key: string): void {
    const parent = parentKey(key);
    if (get().dirs[parent]) void load(parent, null, true);
  }

  /** Erro de bucket inexistente em create/delete: atualiza a lista e repassa o erro. */
  function onManageError(err: unknown): never {
    if (err instanceof ApiError && err.code === "bucket_missing") void loadBuckets();
    throw err;
  }

  return {
    status: null,
    statusError: null,
    retrying: false,
    retryError: null,
    ...EMPTY_TREE,
    start: () => {
      consumers += 1;
      if (consumers > 1) return;
      failures = 0;
      document.addEventListener("visibilitychange", onVisibility);
      if (!document.hidden) void pollStatus();
    },
    stop: () => {
      if (consumers === 0) return;
      consumers -= 1;
      if (consumers > 0) return;
      clearTimer();
      statusController?.abort();
      statusController = null;
      inFlight = false;
      document.removeEventListener("visibilitychange", onVisibility);
    },
    refreshStatus: (force = false) => {
      if (consumers === 0) return;
      if (inFlight) {
        if (!force) return;
        statusController?.abort();
        statusController = null;
        inFlight = false;
      }
      clearTimer();
      void pollStatus();
    },
    reset: () => {
      generation += 1;
      pending.clear();
      lastKey = null;
      set({ ...EMPTY_TREE });
    },
    retry: () => {
      if (get().retrying) return;
      set({ retrying: true, retryError: null });
      retryNotislake()
        .then(() => {
          set({ retrying: false });
          get().refreshStatus();
        })
        .catch((err: unknown) => {
          set({ retrying: false, retryError: errorMessage(err) });
          get().refreshStatus();
        });
    },
    toggle: (key) => {
      if (get().expanded[key]) collapse(key);
      else expand(key);
    },
    expand,
    collapse,
    ensureBuckets: () => {
      const { buckets, bucketsLoading, status } = get();
      if (isNotislakeTreeAvailable(status) && buckets === null && !bucketsLoading) void loadBuckets();
    },
    loadBuckets,
    loadMore: (key) => {
      const d = get().dirs[key];
      if (d && !d.loading && d.nextToken !== null) void load(key, d.nextToken, false);
    },
    refresh: (key) => {
      if (key !== undefined) {
        void load(key, null, true);
        return;
      }
      get().refreshStatus();
      if (!isNotislakeTreeAvailable(get().status)) return;
      void loadBuckets();
      for (const k of Object.keys(get().dirs)) void load(k, null, true);
    },
    refreshExpanded: () => {
      if (!isNotislakeTreeAvailable(get().status)) return;
      if (get().buckets === null) {
        get().ensureBuckets();
        return;
      }
      void reloadBucketsSilently();
      const { expanded } = get();
      const visible = Object.keys(expanded).filter((k) => ancestorsExpanded(k, expanded));
      for (const k of visible) void reloadSilently(k);
    },
    createBucket: async (name) => {
      try {
        await createNotislakeBucket(name);
      } catch (err) {
        onManageError(err);
      }
      await loadBuckets();
      if (get().buckets?.includes(name)) expand(nodeKey(name));
    },
    summary: async (bucket, prefix = "") => {
      try {
        return (await getNotislakeSummary(bucket, prefix)).object_count;
      } catch (err) {
        return onManageError(err);
      }
    },
    deleteBucket: async (bucket, expectedCount) => {
      let deleted: number;
      try {
        ({ deleted } = await deleteNotislakeBucket(bucket, expectedCount));
      } catch (err) {
        return onManageError(err);
      }
      dropSubtree(nodeKey(bucket));
      await loadBuckets();
      return deleted;
    },
    deleteFolder: async (bucket, prefix, expectedCount) => {
      let deleted: number;
      try {
        ({ deleted } = await deleteNotislakeFolder(bucket, prefix, expectedCount));
      } catch (err) {
        return onManageError(err);
      }
      const key = nodeKey(bucket, prefix);
      dropSubtree(key);
      reloadParent(key);
      return deleted;
    },
    deleteObject: async (bucket, objectKey) => {
      let deleted: number;
      try {
        ({ deleted } = await deleteNotislakeObject(bucket, objectKey));
      } catch (err) {
        return onManageError(err);
      }
      reloadParent(nodeKey(bucket, objectKey));
      return deleted;
    },
  };
});
