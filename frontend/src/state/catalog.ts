/**
 * Estado da seção Catalog: resposta do catálogo persistente, nós expandidos e
 * colunas carregadas sob demanda (uma requisição por tabela). O catálogo não
 * depende de sessão de kernel; nada é lido até `refresh()` ser chamado, o que
 * a UI só faz depois de `bootstrapAuth()` resolver "ok".
 */
import { create } from "zustand";
import {
  getCatalog,
  getColumns,
  type CatalogColumn,
  type CatalogResponse,
  type ColumnsQuery,
} from "../api/catalog";
import { ApiError, errorMessage } from "../api/http";

export interface ColumnsState {
  loading: boolean;
  error: string | null;
  items: CatalogColumn[] | null;
}

interface CatalogState {
  loading: boolean;
  data: CatalogResponse | null;
  error: string | null;
  expanded: Record<string, true>;
  columns: Record<string, ColumnsState>;
  /** Relê o catálogo e as colunas das tabelas expandidas. */
  refresh: () => void;
  toggle: (key: string, table?: ColumnsQuery) => void;
  expand: (key: string, table?: ColumnsQuery) => void;
  collapse: (key: string) => void;
  /** Esquece a expansão e as colunas do schema excluído e de tudo sob ele. */
  forgetSchema: (catalog: string, schema: string) => void;
}

/** Chave do nó de schema, compartilhada com a árvore do CatalogSection. */
export function schemaKey(catalog: string, schema: string): string {
  return `c:${catalog}\u0000d:${schema}`;
}

/** Invalida respostas do catálogo em voo quando há um refresh novo. */
let generation = 0;
/** Última requisição de colunas por nó; só a mais recente aplica o resultado. */
const columnReqs = new Map<string, number>();
let columnSeq = 0;
/** Consulta de colunas por nó de tabela, para recarregar no refresh. */
const queries = new Map<string, ColumnsQuery>();

/** Mensagem curta para 409/503 do backend; o resto segue o texto do `detail`. */
function friendlyError(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) return "Catalog database unavailable. Try again.";
  if (err instanceof ApiError && err.status === 409) return "Table metadata unavailable.";
  if (err instanceof ApiError && err.status === 404) return "Table no longer exists.";
  return errorMessage(err);
}

export const useCatalog = create<CatalogState>((set, get) => {
  function loadColumns(key: string, query: ColumnsQuery) {
    const req = ++columnSeq;
    columnReqs.set(key, req);
    queries.set(key, query);
    set((s) => ({ columns: { ...s.columns, [key]: { loading: true, error: null, items: s.columns[key]?.items ?? null } } }));
    getColumns(query)
      .then((items) => {
        if (columnReqs.get(key) !== req) return;
        set((s) => ({ columns: { ...s.columns, [key]: { loading: false, error: null, items } } }));
      })
      .catch((err: unknown) => {
        if (columnReqs.get(key) !== req) return;
        set((s) => ({ columns: { ...s.columns, [key]: { loading: false, error: friendlyError(err), items: null } } }));
      });
  }

  return {
    loading: false,
    data: null,
    error: null,
    expanded: {},
    columns: {},

    refresh: () => {
      const { expanded, columns } = get();
      // Entradas de nós recolhidos (inclusive "Loading…" em voo) são descartadas e recarregadas no expand.
      const kept: Record<string, ColumnsState> = {};
      for (const [key, col] of Object.entries(columns)) {
        if (expanded[key]) kept[key] = col;
        else {
          columnReqs.delete(key);
          queries.delete(key);
        }
      }
      set({ columns: kept, loading: true, error: null });
      const gen = ++generation;
      getCatalog()
        .then((data) => {
          if (gen !== generation) return;
          set({ data, loading: false, error: null });
          const open = get().expanded;
          for (const key of Object.keys(get().columns)) {
            const q = queries.get(key);
            if (open[key] && q) loadColumns(key, q);
          }
        })
        .catch((err: unknown) => {
          if (gen !== generation) return;
          set({ loading: false, error: friendlyError(err) });
        });
    },

    toggle: (key, table) => {
      if (get().expanded[key]) get().collapse(key);
      else get().expand(key, table);
    },

    expand: (key, table) => {
      if (get().expanded[key]) return;
      set((s) => ({ expanded: { ...s.expanded, [key]: true } }));
      if (table) {
        const col = get().columns[key];
        if (!col || (!col.loading && col.items === null)) loadColumns(key, table);
      }
    },

    collapse: (key) =>
      set((s) => {
        const { [key]: _removed, ...rest } = s.expanded;
        return { expanded: rest };
      }),

    forgetSchema: (catalog, schema) => {
      const base = schemaKey(catalog, schema);
      const under = (key: string) => key === base || key.startsWith(`${base}\u0000`);
      for (const key of [...columnReqs.keys()]) {
        if (under(key)) {
          columnReqs.delete(key);
          queries.delete(key);
        }
      }
      set((s) => ({
        expanded: Object.fromEntries(Object.entries(s.expanded).filter(([k]) => !under(k))) as Record<string, true>,
        columns: Object.fromEntries(Object.entries(s.columns).filter(([k]) => !under(k))),
      }));
    },
  };
});
