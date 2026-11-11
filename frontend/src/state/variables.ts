/**
 * Estado do painel Variables: lista de nível superior da sessão de kernel
 * ativa, nós expandidos e filhos carregados sob demanda (cache por caminho,
 * paginados). Tudo é descartado quando a sessão muda ou o kernel deixa de
 * responder. O backend roda uma sondagem por vez: `busy` + `stale` com o
 * kernel idle significa sondagem em voo, e a releitura usa backoff.
 */
import { create } from "zustand";
import { errorMessage } from "../api/http";
import type { VariableChild, VariablePathStep, VariablesResponse } from "../api/types";
import { getVariableChildren, getVariables } from "../api/variables";

export const CHILDREN_PAGE = 100;
/** Chave do nó "Special Variables" em `expanded`. */
export const SPECIAL_KEY = "__special__";

export interface ChildrenState {
  loading: boolean;
  error: string | null;
  items: VariableChild[];
  total: number;
  stale: boolean;
}

interface VariablesState {
  sessionId: string | null;
  loading: boolean;
  data: VariablesResponse | null;
  error: string | null;
  expanded: Record<string, true>;
  children: Record<string, ChildrenState>;
  /** Releituras automáticas já feitas desde o último refresh. */
  retries: number;
  bind: (sessionId: string | null) => void;
  refresh: () => void;
  /** Agenda releitura com backoff; devolve o cancelamento ou null quando as tentativas acabaram. */
  scheduleRetry: () => (() => void) | null;
  toggle: (path: VariablePathStep[]) => void;
  toggleSpecial: () => void;
  /**
   * Liga as leituras ao estado do painel/kernel: só lê com o painel aberto e a
   * sessão viva; primeira leitura imediata, depois a cada transição para idle
   * (debounce cancelado se voltar a busy). Fora de idle/busy solta a sessão.
   */
  sync: (input: { open: boolean; sessionId: string | null; kernelState: string | null }) => void;
  /** Carrega a próxima página de filhos (ou a primeira, se ainda não há). */
  loadMore: (path: VariablePathStep[]) => void;
}

const EMPTY = {
  loading: false,
  data: null,
  error: null,
  expanded: {} as Record<string, true>,
  children: {} as Record<string, ChildrenState>,
  retries: 0,
};

const BACKOFF_MS = [1000, 2000, 4000, 4000, 4000];
export const VARIABLES_MAX_RETRIES = BACKOFF_MS.length;

export const pathKey = (path: VariablePathStep[]): string => JSON.stringify(path);

/** Invalida respostas em voo quando a sessão muda ou há novo refresh. */
let generation = 0;
/** Só a requisição mais recente de cada caminho aplica o resultado. */
const childReqs = new Map<string, number>();
let childSeq = 0;
/** Nós cujo fetch em voo foi invalidado por `load()` (ficam vazios, sem erro, até novo fetch). */
const cancelledKeys = new Set<string>();
const childTimers = new Set<ReturnType<typeof setTimeout>>();
/** Espera depois de o kernel voltar a idle antes de reler (evita sondar a cada célula). */
const REFRESH_DEBOUNCE_MS = 1500;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
/** Último estado do kernel informado por `sync`; decide se `stale` com idle é sondagem em voo. */
let kernelIdle = false;
/** Fila serial de releitura dos filhos expandidos (um por vez). */
let childQueue: string[] = [];

const clearRefreshTimer = () => {
  if (refreshTimer !== null) clearTimeout(refreshTimer);
  refreshTimer = null;
};

/** Verdadeiro se `key` é o próprio `prefix` ou um descendente dele. */
function isUnder(key: string, prefix: VariablePathStep[]): boolean {
  if (key === SPECIAL_KEY) return false;
  let path: VariablePathStep[];
  try {
    path = JSON.parse(key) as VariablePathStep[];
  } catch {
    return false;
  }
  return path.length >= prefix.length && prefix.every((step, i) => JSON.stringify(step) === JSON.stringify(path[i]));
}

export const useVariables = create<VariablesState>((set, get) => {
  const patchChild = (key: string, patch: Partial<ChildrenState>) =>
    set((s) => ({
      children: {
        ...s.children,
        [key]: { loading: false, error: null, items: [], total: 0, stale: false, ...s.children[key], ...patch },
      },
    }));

  function nextQueued(gen: number) {
    if (gen !== generation) return;
    const key = childQueue.shift();
    if (key === undefined) return;
    if (!get().expanded[key]) {
      nextQueued(gen);
      return;
    }
    fetchChildren(JSON.parse(key) as VariablePathStep[], 0, true, 0, () => nextQueued(gen));
  }

  function dropSubtree(path: VariablePathStep[]) {
    set((s) => {
      const expanded = { ...s.expanded };
      const children = { ...s.children };
      for (const key of Object.keys(s.expanded)) if (isUnder(key, path)) delete expanded[key];
      for (const key of Object.keys(s.children)) {
        if (!isUnder(key, path)) continue;
        delete children[key];
        childReqs.delete(key);
      }
      return { expanded, children };
    });
  }

  function fetchChildren(path: VariablePathStep[], offset: number, replace: boolean, attempt = 0, done?: () => void) {
    const { sessionId } = get();
    if (!sessionId) return;
    const key = pathKey(path);
    const req = ++childSeq;
    childReqs.set(key, req);
    cancelledKeys.delete(key);
    const gen = generation;
    patchChild(key, { loading: true, error: null });
    getVariableChildren(sessionId, path, offset, CHILDREN_PAGE)
      .then((res) => {
        if (childReqs.get(key) !== req || gen !== generation) return;
        if (res.status === "stale_path") {
          // O caminho deixou de existir: descarta o nó e os descendentes antes de reler.
          dropSubtree(path);
          get().refresh();
          return;
        }
        const retryable = res.status === "busy" || (res.status === "ok" && res.stale && kernelIdle);
        if (retryable && attempt < BACKOFF_MS.length) {
          patchChild(key, { loading: true, stale: true });
          const timer = setTimeout(() => {
            childTimers.delete(timer);
            if (childReqs.get(key) === req && gen === generation) {
              fetchChildren(path, offset, replace, attempt + 1, done);
            }
          }, BACKOFF_MS[attempt]);
          childTimers.add(timer);
          return;
        }
        if (res.status !== "ok") {
          patchChild(key, { loading: false, error: res.message ?? "Could not read the children." });
          done?.();
          return;
        }
        const prev = replace ? [] : (get().children[key]?.items ?? []);
        patchChild(key, { loading: false, error: null, items: [...prev, ...res.children], total: res.total, stale: res.stale });
        done?.();
      })
      .catch((err: unknown) => {
        if (childReqs.get(key) !== req || gen !== generation) return;
        patchChild(key, { loading: false, error: errorMessage(err) });
        done?.();
      });
  }

  function load() {
    const { sessionId } = get();
    if (!sessionId) return;
    const gen = ++generation;
    childQueue = [];
    // Fetches em voo ficam obsoletos com a nova geração e não limpam `loading`.
    const kept = Object.fromEntries(
      Object.entries(get().children).map(([k, c]) => {
        if (c.loading) cancelledKeys.add(k);
        return [k, { ...c, loading: false }];
      }),
    );
    set({ loading: true, error: null, children: kept });
    getVariables(sessionId)
      .then((data) => {
        if (gen !== generation) return;
        // `busy` sem cache não apaga a lista anterior: mantém o último dado visível.
        const keep = data.status === "busy" && data.variables.length === 0 ? get().data : null;
        set({ data: keep ?? data, loading: false, error: null });
        if (data.status !== "ok") return;
        // Descarta nós expandidos cuja variável raiz não existe mais.
        const names = new Set<VariablePathStep>(data.variables.map((v) => v.name));
        const gone = Object.keys(get().expanded).filter((k) => k !== SPECIAL_KEY && !names.has((JSON.parse(k) as VariablePathStep[])[0] as VariablePathStep));
        for (const k of gone) dropSubtree((JSON.parse(k) as VariablePathStep[]).slice(0, 1));
        const { children, expanded } = get();
        childQueue = Object.keys(children).filter((key) => expanded[key]);
        nextQueued(gen);
      })
      .catch((err: unknown) => {
        if (gen !== generation) return;
        set({ loading: false, error: errorMessage(err) });
      });
  }

  return {
    sessionId: null,
    ...EMPTY,

    bind: (sessionId) => {
      if (get().sessionId === sessionId) return;
      generation++;
      childReqs.clear();
      cancelledKeys.clear();
      childTimers.forEach(clearTimeout);
      childTimers.clear();
      childQueue = [];
      set({ sessionId, ...EMPTY });
    },

    refresh: () => {
      const { expanded, children } = get();
      const kept: Record<string, ChildrenState> = {};
      for (const [key, c] of Object.entries(children)) {
        if (expanded[key]) kept[key] = c;
        else childReqs.delete(key);
      }
      set({ children: kept, retries: 0 });
      load();
    },

    scheduleRetry: () => {
      const { retries } = get();
      if (retries >= BACKOFF_MS.length) return null;
      const timer = setTimeout(() => {
        set({ retries: retries + 1 });
        load();
      }, BACKOFF_MS[retries]);
      return () => clearTimeout(timer);
    },

    toggle: (path) => {
      const key = pathKey(path);
      if (get().expanded[key]) {
        set((s) => {
          const { [key]: _removed, ...rest } = s.expanded;
          return { expanded: rest };
        });
        return;
      }
      set((s) => ({ expanded: { ...s.expanded, [key]: true } }));
      const c = get().children[key];
      // Também refaz o fetch do nó cujo carregamento `load()` cancelou (ficou vazio, sem erro).
      const cancelled = cancelledKeys.delete(key);
      if (!c || (!c.loading && c.items.length === 0 && (c.error !== null || cancelled))) fetchChildren(path, 0, true);
    },

    toggleSpecial: () =>
      set((s) => {
        if (s.expanded[SPECIAL_KEY]) {
          const { [SPECIAL_KEY]: _removed, ...rest } = s.expanded;
          return { expanded: rest };
        }
        return { expanded: { ...s.expanded, [SPECIAL_KEY]: true } };
      }),

    sync: ({ open, sessionId, kernelState }) => {
      clearRefreshTimer();
      const live = open && Boolean(sessionId) && (kernelState === "idle" || kernelState === "busy");
      kernelIdle = live && kernelState === "idle";
      if (!live) {
        get().bind(null);
        return;
      }
      get().bind(sessionId);
      if (get().data === null) {
        get().refresh();
        return;
      }
      if (kernelState !== "idle") return;
      refreshTimer = setTimeout(() => {
        refreshTimer = null;
        if (!document.hidden) get().refresh();
      }, REFRESH_DEBOUNCE_MS);
    },

    loadMore: (path) => {
      const c = get().children[pathKey(path)];
      if (c?.loading) return;
      fetchChildren(path, c?.items.length ?? 0, !c);
    },
  };
});
