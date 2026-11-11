/**
 * Store de UM notebook aberto (zustand vanilla, uma instância por aba).
 * `createNotebookStore(path)` cria a instância; o registro das abas abertas
 * (mapa path → stores) fica em `state/workspace.ts` e os componentes leem a
 * instância da aba via contexto (`state/notebookContext.tsx`).
 * Fonte única do estado de edição: células, seleção/modo (comando × edição),
 * alterações não salvas e salvamento.
 *
 * Fidelidade ao disco: o notebook é mantido como nbformat v4 com `source`
 * normalizado para string. `toNotebook()` serializa preservando `metadata`
 * (inclui `metadata.kernelspec`), `nbformat`/`nbformat_minor`, `id` das
 * células, `metadata` de cada célula e `outputs`/`execution_count` existentes
 * das células code — nada que veio do disco é descartado, exceto campos que o
 * schema proíbe após uma troca de tipo (ex.: `outputs` ao virar markdown).
 *
 * Pontos de extensão:
 * - Execução: `appendOutput`, `clearOutputs`, `setExecutionCount`
 *   alteram as saídas de uma célula code; `NotebookView.onRunCell` dispara.
 * - Seletor de kernel: `setKernelspec(name, display_name, language)`.
 * - Título da célula em `metadata.title` (`setCellTitle`).
 * - Linguagem da célula code em `metadata.notisbook.language` (`setCellLanguage`);
 *   ausente = python.
 *
 * Este módulo não toca `window` nem o DOM (roda também fora do navegador).
 */
import { createStore, type StoreApi } from "zustand/vanilla";
import { ApiError, errorMessage } from "../api/http";
import { getNotebook, saveNotebook } from "../api/contents";
import type {
  Cell,
  CodeCell,
  MarkdownCell,
  Notebook,
  NotebookMetadata,
  Output,
  RawCell,
} from "../api/nbformat";
import { joinMultiline } from "../api/nbformat";

export type CellType = Cell["cell_type"];
/** Tipos que a UI cria/alterna (raw só é preservado quando vem do disco). */
export type EditableCellType = "code" | "markdown";

type WithEditorFields<T> = Omit<T, "id" | "source"> & { id: string; source: string };
export type EditorCodeCell = WithEditorFields<CodeCell>;
export type EditorMarkdownCell = WithEditorFields<MarkdownCell>;
export type EditorRawCell = WithEditorFields<RawCell>;
/** Célula em edição: `id` sempre presente e `source` como string única. */
export type EditorCell = EditorCodeCell | EditorMarkdownCell | EditorRawCell;

export type EditorMode = "command" | "edit";
export type LoadStatus = "idle" | "loading" | "ready" | "error";
export type InsertWhere = "above" | "below";

/** nbformat 4.5 introduziu `id` nas células; abaixo disso o schema o proíbe. */
const MIN_MINOR_WITH_IDS = 5;
const ID_PATTERN = /^[a-zA-Z0-9-_]{1,64}$/;

export function newCellId(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  let s = "";
  for (let i = 0; i < 32; i += 1) s += Math.floor(Math.random() * 16).toString(16);
  return s;
}

export function createCell(type: EditableCellType, source = ""): EditorCell {
  if (type === "code") {
    return { id: newCellId(), cell_type: "code", metadata: {}, source, execution_count: null, outputs: [] };
  }
  return { id: newCellId(), cell_type: "markdown", metadata: {}, source };
}

function toEditorCell(cell: Cell, seen: Set<string>): EditorCell {
  let id = typeof cell.id === "string" && ID_PATTERN.test(cell.id) && !seen.has(cell.id) ? cell.id : newCellId();
  while (seen.has(id)) id = newCellId();
  seen.add(id);
  const source = joinMultiline(cell.source ?? "");
  const metadata = cell.metadata ?? {};
  if (cell.cell_type === "code") {
    return {
      ...cell,
      id,
      source,
      metadata,
      execution_count: cell.execution_count ?? null,
      outputs: Array.isArray(cell.outputs) ? cell.outputs : [],
    };
  }
  return { ...cell, id, source, metadata };
}

/** Troca o tipo mantendo id/source/metadata e removendo campos que o novo tipo não admite. */
function convertCell(cell: EditorCell, type: CellType): EditorCell {
  if (cell.cell_type === type) return cell;
  const base = { id: cell.id, source: cell.source, metadata: cell.metadata };
  if (type === "code") return { ...base, cell_type: "code", execution_count: null, outputs: [] };
  const attachments = cell.cell_type !== "code" ? cell.attachments : undefined;
  const converted = { ...base, cell_type: type, ...(attachments ? { attachments } : {}) };
  return converted as EditorMarkdownCell | EditorRawCell;
}

export interface NotebookDocument {
  nbformat: 4;
  nbformat_minor: number;
  metadata: NotebookMetadata;
  cells: EditorCell[];
}

export function fromNotebook(nb: Notebook): NotebookDocument {
  const seen = new Set<string>();
  return {
    nbformat: 4,
    nbformat_minor: Math.max(nb.nbformat_minor ?? MIN_MINOR_WITH_IDS, MIN_MINOR_WITH_IDS),
    metadata: nb.metadata ?? {},
    cells: (nb.cells ?? []).map((c) => toEditorCell(c, seen)),
  };
}

/** Serializa o estado para o JSON nbformat v4 enviado ao `PUT /api/contents/{path}`. */
export function toNotebook(doc: NotebookDocument): Notebook {
  const cells: Cell[] = doc.cells.map((cell) => {
    if (cell.cell_type === "code") {
      const { id, cell_type, metadata, source, execution_count, outputs, ...rest } = cell;
      return { ...rest, id, cell_type, metadata, source, execution_count, outputs };
    }
    const { id, cell_type, metadata, source, ...rest } = cell;
    return { ...rest, id, cell_type, metadata, source };
  });
  return {
    nbformat: 4,
    nbformat_minor: Math.max(doc.nbformat_minor, MIN_MINOR_WITH_IDS),
    metadata: doc.metadata,
    cells,
  };
}

/** Junta saídas `stream` consecutivas do mesmo canal (como o Jupyter). */
function mergeOutput(outputs: Output[], output: Output): Output[] {
  const last = outputs[outputs.length - 1];
  if (output.output_type === "stream" && last?.output_type === "stream" && last.name === output.name) {
    const merged: Output = { ...last, text: joinMultiline(last.text) + joinMultiline(output.text) };
    return [...outputs.slice(0, -1), merged];
  }
  return [...outputs, output];
}

export interface NotebookState extends NotebookDocument {
  /** Caminho do notebook desta instância (fixo). */
  path: string;
  status: LoadStatus;
  loadError: string | null;

  /** Célula selecionada e modo de teclado (estilo Jupyter). */
  activeId: string | null;
  mode: EditorMode;
  /** Células markdown abertas no editor (as demais aparecem renderizadas). */
  editingMarkdown: Record<string, boolean>;

  /** Há alterações não salvas. */
  dirty: boolean;
  /** Incrementa a cada alteração; o save só limpa `dirty` se nada mudou durante o PUT. */
  revision: number;
  saving: boolean;
  saveError: string | null;
  lastSavedAt: number | null;

  // Ciclo de vida
  /** (Re)carrega do disco, descartando o estado em memória. */
  load: () => Promise<void>;
  /** PUT do notebook inteiro. Resolve `true` se salvou. */
  save: () => Promise<boolean>;

  // Edição
  setSource: (id: string, source: string) => void;
  /** Insere relativo a `refId` (ou no fim/início quando null). Devolve o id criado. */
  insertCell: (where: InsertWhere, refId: string | null, type: EditableCellType) => string;
  deleteCell: (id: string) => void;
  moveCell: (id: string, delta: -1 | 1) => void;
  changeCellType: (id: string, type: EditableCellType) => void;
  /** Grava `metadata.title` (string vazia/null remove a chave). */
  setCellTitle: (id: string, title: string | null) => void;
  /**
   * Troca a linguagem de uma célula code: grava/remove `metadata.notisbook.language`,
   * reescreve o `source` (`switchLanguageSource`) e apaga saídas e execution_count.
   */
  setCellLanguage: (id: string, language: CellLanguage) => void;

  // Seleção / modo
  selectCell: (id: string, mode?: EditorMode) => void;
  /** Seleciona a célula vizinha; devolve o id selecionado (ou null). */
  selectAdjacent: (delta: -1 | 1) => string | null;
  setMode: (mode: EditorMode) => void;
  setMarkdownEditing: (id: string, editing: boolean) => void;

  // Kernel
  setKernelspec: (name: string, displayName: string, language?: string) => void;

  // Execução / saídas
  appendOutput: (id: string, output: Output) => void;
  clearOutputs: (id: string) => void;
  setExecutionCount: (id: string, count: number | null) => void;
}

export type NotebookStore = StoreApi<NotebookState>;

/** Título da célula (`metadata.title`) ou null. */
export function cellTitle(cell: EditorCell): string | null {
  const t = cell.metadata.title;
  return typeof t === "string" && t.trim() ? t : null;
}

export type CellLanguage = "python" | "sql" | "duckdb";

const CELL_LANGUAGES: readonly CellLanguage[] = ["sql", "duckdb"];

/** Família que define as marcas de comentário: Spark SQL e DuckDB SQL são ambos SQL. */
export type LanguageFamily = "python" | "sql";

export function languageFamily(language: CellLanguage): LanguageFamily {
  return language === "python" ? "python" : "sql";
}

/** Linguagem da célula code (`metadata.notisbook.language`); ausente ou desconhecida = python. */
export function cellLanguage(cell: EditorCell): CellLanguage {
  const ns = cell.metadata.notisbook;
  const lang = ns && typeof ns === "object" ? (ns as Record<string, unknown>).language : undefined;
  return CELL_LANGUAGES.find((l) => l === lang) ?? "python";
}

/**
 * Marca que comenta, no documento de uma família, as linhas escritas na outra:
 * em SQL as linhas Python viram `-- [py] ...`; em Python as linhas SQL viram `# [sql] ...`.
 */
export const LANGUAGE_COMMENT_MARK: Record<LanguageFamily, string> = {
  sql: "-- [py] ",
  python: "# [sql] ",
};

/**
 * Reescreve o código ao trocar de linguagem sem perder nada: linhas que carregam a
 * marca do documento de origem (código da linguagem de destino) são descomentadas e as
 * demais não vazias são comentadas com a marca do destino. Comentários escritos à mão
 * (sem a marca) nunca são descomentados; linhas vazias e células vazias ficam intactas.
 */
export function switchLanguageSource(source: string, from: CellLanguage, to: CellLanguage): string {
  const fromFamily = languageFamily(from);
  const toFamily = languageFamily(to);
  // Mesma família (Spark SQL <-> DuckDB SQL): o fonte já está na linguagem certa.
  if (fromFamily === toFamily || source.trim() === "") return source;
  const fromMark = LANGUAGE_COMMENT_MARK[fromFamily];
  const toMark = LANGUAGE_COMMENT_MARK[toFamily];
  return source
    .split("\n")
    .map((line) => {
      if (line.trim() === "") return line;
      return line.startsWith(fromMark) ? line.slice(fromMark.length) : toMark + line;
    })
    .join("\n");
}

const EMPTY_DOC: NotebookDocument = { nbformat: 4, nbformat_minor: MIN_MINOR_WITH_IDS, metadata: {}, cells: [] };

const INITIAL = {
  ...EMPTY_DOC,
  status: "idle" as LoadStatus,
  loadError: null,
  activeId: null,
  mode: "command" as EditorMode,
  editingMarkdown: {},
  dirty: false,
  revision: 0,
  saving: false,
  saveError: null,
  lastSavedAt: null,
};

export function createNotebookStore(path: string): NotebookStore {
  return createStore<NotebookState>((set, get) => {
    /** Descarta respostas de `load` que chegam depois de outro `load`. */
    let loadToken = 0;

    /** Aplica uma mudança de conteúdo e marca o notebook como alterado. */
    const mutate = (fn: (s: NotebookState) => Partial<NotebookState> | null) => {
      set((s) => {
        const patch = fn(s);
        if (!patch) return s;
        return { ...patch, dirty: true, revision: s.revision + 1, saveError: null };
      });
    };

    const mapCell = (id: string, fn: (c: EditorCell) => EditorCell) =>
      mutate((s) => {
        const i = s.cells.findIndex((c) => c.id === id);
        const cell = s.cells[i];
        if (!cell) return null;
        const next = fn(cell);
        if (next === cell) return null;
        const cells = s.cells.slice();
        cells[i] = next;
        return { cells };
      });

    const mapCodeCell = (id: string, fn: (c: EditorCodeCell) => EditorCodeCell) =>
      mapCell(id, (c) => (c.cell_type === "code" ? fn(c) : c));

    return {
      ...INITIAL,
      path,

      load: async () => {
        const token = ++loadToken;
        set({ ...INITIAL, status: "loading" });
        try {
          const nb = await getNotebook(path);
          if (token !== loadToken) return;
          const doc = fromNotebook(nb);
          set({ ...doc, status: "ready", activeId: doc.cells[0]?.id ?? null });
        } catch (err) {
          if (token !== loadToken) return;
          set({ status: "error", loadError: errorMessage(err) });
        }
      },

      save: async () => {
        const s = get();
        if (s.status !== "ready" || s.saving) return false;
        const startedAt = s.revision;
        set({ saving: true, saveError: null });
        try {
          await saveNotebook(path, toNotebook(s));
          set((cur) => ({
            saving: false,
            lastSavedAt: Date.now(),
            dirty: cur.revision === startedAt ? false : cur.dirty,
          }));
          return true;
        } catch (err) {
          const msg =
            err instanceof ApiError && err.status === 422
              ? `Invalid notebook: ${err.message}`
              : `Failed to save: ${errorMessage(err)}`;
          set({ saving: false, saveError: msg });
          return false;
        }
      },

      setSource: (id, source) => mapCell(id, (c) => (c.source === source ? c : { ...c, source })),

      insertCell: (where, refId, type) => {
        const cell = createCell(type);
        mutate((s) => {
          const ref = refId === null ? -1 : s.cells.findIndex((c) => c.id === refId);
          let index: number;
          if (ref < 0) index = where === "above" ? 0 : s.cells.length;
          else index = where === "above" ? ref : ref + 1;
          const cells = s.cells.slice();
          cells.splice(index, 0, cell);
          const editingMarkdown = type === "markdown" ? { ...s.editingMarkdown, [cell.id]: true } : s.editingMarkdown;
          return { cells, activeId: cell.id, editingMarkdown };
        });
        return cell.id;
      },

      deleteCell: (id) =>
        mutate((s) => {
          const i = s.cells.findIndex((c) => c.id === id);
          if (i < 0) return null;
          const cells = s.cells.filter((c) => c.id !== id);
          const { [id]: _removed, ...editingMarkdown } = s.editingMarkdown;
          const activeId = s.activeId === id ? (cells[Math.min(i, cells.length - 1)]?.id ?? null) : s.activeId;
          return { cells, editingMarkdown, activeId, mode: s.activeId === id ? "command" : s.mode };
        }),

      moveCell: (id, delta) =>
        mutate((s) => {
          const i = s.cells.findIndex((c) => c.id === id);
          const j = i + delta;
          const cell = s.cells[i];
          const other = s.cells[j];
          if (!cell || !other) return null;
          const cells = s.cells.slice();
          cells[i] = other;
          cells[j] = cell;
          return { cells };
        }),

      changeCellType: (id, type) => {
        mapCell(id, (c) => convertCell(c, type));
        if (type === "markdown") set((s) => ({ editingMarkdown: { ...s.editingMarkdown, [id]: true } }));
      },

      setCellTitle: (id, title) =>
        mapCell(id, (c) => {
          const next = title?.trim() ? title.trim() : null;
          if ((cellTitle(c) ?? null) === next) return c;
          const { title: _old, ...rest } = c.metadata;
          return { ...c, metadata: next ? { ...rest, title: next } : rest };
        }),

      setCellLanguage: (id, language) =>
        mapCodeCell(id, (c) => {
          const from = cellLanguage(c);
          if (from === language) return c;
          const { notisbook, ...rest } = c.metadata;
          const ns = notisbook && typeof notisbook === "object" ? (notisbook as Record<string, unknown>) : {};
          const { language: _old, ...nsRest } = ns;
          const nextNs = language === "python" ? nsRest : { ...nsRest, language };
          const metadata = Object.keys(nextNs).length > 0 ? { ...rest, notisbook: nextNs } : rest;
          return {
            ...c,
            metadata,
            source: switchLanguageSource(c.source, from, language),
            outputs: [],
            execution_count: null,
          };
        }),

      selectCell: (id, mode) => set((s) => ({ activeId: id, mode: mode ?? s.mode })),

      selectAdjacent: (delta) => {
        const s = get();
        const i = s.cells.findIndex((c) => c.id === s.activeId);
        const next = s.cells[i < 0 ? 0 : i + delta];
        if (!next) return null;
        set({ activeId: next.id });
        return next.id;
      },

      setMode: (mode) => set({ mode }),

      setMarkdownEditing: (id, editing) =>
        set((s) => {
          if (Boolean(s.editingMarkdown[id]) === editing) return s;
          const { [id]: _prev, ...rest } = s.editingMarkdown;
          return { editingMarkdown: editing ? { ...rest, [id]: true } : rest };
        }),

      setKernelspec: (name, displayName, language = "python") =>
        mutate((s) => {
          const ks = s.metadata.kernelspec;
          if (ks && ks.name === name && ks.display_name === displayName && ks.language === language) return null;
          return { metadata: { ...s.metadata, kernelspec: { ...ks, name, display_name: displayName, language } } };
        }),

      appendOutput: (id, output) => mapCodeCell(id, (c) => ({ ...c, outputs: mergeOutput(c.outputs, output) })),

      clearOutputs: (id) => mapCodeCell(id, (c) => (c.outputs.length === 0 ? c : { ...c, outputs: [] })),

      setExecutionCount: (id, count) =>
        mapCodeCell(id, (c) => (c.execution_count === count ? c : { ...c, execution_count: count })),
    };
  });
}
