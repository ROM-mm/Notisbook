/**
 * Estado do painel Notislake (MinIO/S3): status da conexão com polling e
 * listagens por prefixo sob demanda. O polling usa setTimeout encadeado (nunca
 * sobrepõe leituras), é contado por consumidor (`start`/`stop`) e pausa com a
 * aba oculta. O store não recebe nem guarda credenciais: o diálogo de
 * configuração chama a API direto.
 */
import { create } from "zustand";
import { errorMessage } from "../api/http";
import {
  getNotislakeStatus,
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
  /** Bucket da última listagem; base do caminho `s3a://`. */
  bucket: string | null;
  expanded: Record<string, true>;
  /** Listagens por prefixo; a raiz do bucket é a chave `""`. */
  dirs: Record<string, NotislakeDirState>;
  start: () => void;
  stop: () => void;
  /** Com `force`, aborta a leitura em andamento e reemite; sem ele, é ignorado se já houver uma. */
  refreshStatus: (force?: boolean) => void;
  /** Descarta árvore e cache (nova conexão): invalida listagens em voo e zera bucket/expansão. */
  reset: () => void;
  retry: () => void;
  toggle: (prefix: string) => void;
  expand: (prefix: string) => void;
  collapse: (prefix: string) => void;
  /** Carrega a raiz do bucket se ainda não houver listagem válida. */
  loadRoot: () => void;
  loadMore: (prefix: string) => void;
  /** Sem argumento recarrega o status e todos os prefixos carregados; com prefixo, só ele. */
  refresh: (prefix?: string) => void;
  /** Recarrega em silêncio a raiz e os prefixos expandidos, sem status e sem encolher o que já foi paginado. */
  refreshExpanded: () => void;
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

/** Verdadeiro se todo ancestral do prefixo (`a/`, `a/b/`) está expandido; a raiz `""` é sempre visível. */
function ancestorsExpanded(prefix: string, expanded: Record<string, true>): boolean {
  const parts = prefix.split("/").filter(Boolean);
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
      useNotislake.setState({ status, statusError: null, bucket: null, expanded: {}, dirs: {} });
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
  /** Prefixos em recarga silenciosa; evitam duas recargas simultâneas do mesmo prefixo. */
  const silent = new Set<string>();
  /** Prefixos que pediram recarga durante uma em andamento; rodam uma vez ao fim dela. */
  const pending = new Set<string>();
  /** Contador de ações manuais por prefixo; a recarga silenciosa descarta o resultado se ele mudou. */
  const manualStamp = new Map<string, number>();

  async function load(prefix: string, token: string | null, replace: boolean): Promise<void> {
    const gen = generation;
    const prev = get().dirs[prefix];
    if (prev?.loading) return;
    manualStamp.set(prefix, (manualStamp.get(prefix) ?? 0) + 1);
    set((s) => ({
      dirs: {
        ...s.dirs,
        [prefix]: {
          prefixes: prev?.prefixes ?? [],
          objects: prev?.objects ?? [],
          nextToken: prev?.nextToken ?? null,
          loading: true,
          error: null,
        },
      },
    }));
    try {
      const page = await listNotislakeObjects({ prefix, maxKeys: PAGE_SIZE, continuationToken: token });
      if (gen !== generation) return;
      set((s) => {
        const base = replace ? undefined : s.dirs[prefix];
        const prefixes = [...(base?.prefixes ?? []), ...page.prefixes];
        const objects = [...(base?.objects ?? []), ...page.objects];
        return {
          bucket: page.bucket,
          dirs: {
            ...s.dirs,
            [prefix]: {
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
      if (gen !== generation) return;
      set((s) => {
        const cur = s.dirs[prefix];
        return {
          dirs: {
            ...s.dirs,
            [prefix]: {
              prefixes: cur?.prefixes ?? [],
              objects: cur?.objects ?? [],
              nextToken: cur?.nextToken ?? null,
              loading: false,
              error: errorMessage(err),
            },
          },
        };
      });
    }
  }

  async function reloadSilently(prefix: string): Promise<void> {
    const gen = generation;
    const prev = get().dirs[prefix];
    if (!prev || prev.loading || prev.error) return;
    if (silent.has(prefix)) {
      pending.add(prefix);
      return;
    }
    silent.add(prefix);
    const stamp = manualStamp.get(prefix) ?? 0;
    const stale = () => gen !== generation || (manualStamp.get(prefix) ?? 0) !== stamp;
    const target = prev.prefixes.length + prev.objects.length;
    try {
      const prefixes: string[] = [];
      const objects: NotislakeObject[] = [];
      let token: string | null = null;
      let bucket: string | null = null;
      let truncated = false;
      do {
        const page = await listNotislakeObjects({ prefix, maxKeys: PAGE_SIZE, continuationToken: token });
        if (stale()) return;
        prefixes.push(...page.prefixes);
        objects.push(...page.objects);
        bucket = page.bucket;
        truncated = page.is_truncated;
        token = truncated ? page.next_continuation_token : null;
      } while (truncated && token !== null && new Set(prefixes).size + objects.length < target);
      if (stale()) return;
      set((s) => ({
        bucket,
        dirs: {
          ...s.dirs,
          [prefix]: { prefixes: [...new Set(prefixes)], objects, nextToken: token, loading: false, error: null },
        },
      }));
    } catch {
      // Falha na recarga automática mantém a listagem atual; o Retry manual segue disponível.
    } finally {
      silent.delete(prefix);
      if (pending.delete(prefix)) void reloadSilently(prefix);
    }
  }

  function expand(prefix: string): void {
    set((s) => ({ expanded: { ...s.expanded, [prefix]: true } }));
    const d = get().dirs[prefix];
    if (!d || d.error) void load(prefix, null, true);
  }

  return {
    status: null,
    statusError: null,
    retrying: false,
    retryError: null,
    bucket: null,
    expanded: {},
    dirs: {},
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
      set({ bucket: null, expanded: {}, dirs: {} });
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
    toggle: (prefix) => {
      if (get().expanded[prefix]) get().collapse(prefix);
      else expand(prefix);
    },
    expand,
    collapse: (prefix) =>
      set((s) => {
        const { [prefix]: _removed, ...rest } = s.expanded;
        return { expanded: rest };
      }),
    loadRoot: () => {
      const d = get().dirs[""];
      if (isNotislakeTreeAvailable(get().status) && (!d || d.error)) void load("", null, true);
    },
    loadMore: (prefix) => {
      const d = get().dirs[prefix];
      if (d && !d.loading && d.nextToken !== null) void load(prefix, d.nextToken, false);
    },
    refresh: (prefix) => {
      if (prefix !== undefined) {
        void load(prefix, null, true);
        return;
      }
      get().refreshStatus();
      if (!isNotislakeTreeAvailable(get().status)) return;
      for (const key of Object.keys(get().dirs)) void load(key, null, true);
    },
    refreshExpanded: () => {
      if (!isNotislakeTreeAvailable(get().status)) return;
      if (!get().dirs[""]) {
        get().loadRoot();
        return;
      }
      const { expanded } = get();
      const visible = Object.keys(expanded).filter((key) => ancestorsExpanded(key, expanded));
      for (const key of ["", ...visible]) void reloadSilently(key);
    },
  };
});
