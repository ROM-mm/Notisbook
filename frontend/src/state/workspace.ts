/**
 * Workspace: notebooks abertos em abas, painel lateral e diálogos.
 *
 * Modelo multi-notebook: cada aba é um `NotebookEntry` com seu próprio store
 * de notebook (`createNotebookStore`) e sua própria sessão de kernel
 * (`createKernelStore`). As entradas vivem num mapa path → entry fora do
 * estado reativo; `tabs` (ordem das abas) é reativo. A aba ATIVA é a da rota
 * (`/notebooks/<path>`); abrir uma rota de notebook cria a aba se preciso.
 * Trocar de aba preserva tudo (células, saídas, rodapés, sessão, scroll);
 * fechar a aba encerra a sessão do kernel (`DELETE /api/sessions/{id}`).
 */
import { create } from "zustand";
import { createEntry, listDir } from "../api/contents";
import { getRootGeneration, setRootGeneration } from "../api/http";
import { listKernelspecs } from "../api/kernels";
import { getNotebooksRoot, type NotebooksRoot } from "../api/notebooksRoot";
import { joinPath, NOTEBOOK_EXT, uniqueName } from "../lib/paths";
import { createKernelStore, type KernelStore } from "./kernel";
import { createNotebookStore, type NotebookStore } from "./notebook";
import { useNotebookTree } from "./notebookTree";
import { openHome, openNotebook, useRouter } from "./router";

export interface NotebookEntry {
  path: string;
  notebook: NotebookStore;
  kernel: KernelStore;
  /** Estado de view não reativo preservado entre trocas de aba. */
  view: { scrollTop: number };
}

export type SidePanel = "data" | "notebooks";
export type RightPanel = "variables";

export const UNSAVED_MESSAGE = "This notebook has unsaved changes. Close anyway?";

const entries = new Map<string, NotebookEntry>();

export function getEntry(path: string): NotebookEntry | undefined {
  return entries.get(path);
}

/** Algum dos `paths` (ou um notebook sob um diretório em `paths`) está aberto? */
export function isOpenUnder(path: string): boolean {
  for (const p of entries.keys()) if (p === path || p.startsWith(`${path}/`)) return true;
  return false;
}

/**
 * Relê `GET /api/kernelspecs` e atualiza a lista de TODAS as abas abertas
 * (após instalar/remover um ambiente Spark ou ao abrir o seletor de ambiente).
 */
export async function refreshKernelspecs(): Promise<void> {
  const specs = await listKernelspecs();
  for (const entry of entries.values()) entry.kernel.setState({ kernelspecs: specs });
}

/** Carrega o notebook e, se carregou, abre a sessão do kernel. */
async function start(entry: NotebookEntry): Promise<void> {
  await entry.notebook.getState().load();
  if (entries.get(entry.path) !== entry) return;
  if (entry.notebook.getState().status === "ready") void entry.kernel.getState().open();
}

interface WorkspaceState {
  /** Paths dos notebooks abertos, na ordem das abas. */
  tabs: string[];
  /** Painel lateral aberto (null = recolhido). */
  panel: SidePanel | null;
  /** Rail visível: false no início limpo; vira true na primeira abertura de painel e fica. */
  railVisible: boolean;
  /** Modo foco: oculta rail, painel lateral e Variables sem alterar `panel`/`rightPanel`. */
  focusMode: boolean;
  /** Painel direito (independente do lateral); null = recolhido. */
  rightPanel: RightPanel | null;
  /** Raiz dos notebooks (null até carregar; só carrega depois de `bootstrapAuth()`). */
  root: NotebooksRoot | null;
  shortcutsOpen: boolean;
  aboutOpen: boolean;

  /** Garante a aba (cria stores, carrega, abre o kernel). Não navega. */
  ensureTab: (path: string) => NotebookEntry;
  /** Recarrega do disco e reabre a sessão. */
  reload: (path: string) => void;
  /** Fecha a aba (pede confirmação se houver alterações). Devolve `false` se cancelado. */
  closeTab: (path: string) => boolean;
  togglePanel: (panel: SidePanel) => void;
  setPanel: (panel: SidePanel | null) => void;
  toggleFocusMode: () => void;
  toggleRightPanel: (panel: RightPanel) => void;
  setRightPanel: (panel: RightPanel | null) => void;
  /** Busca a raiz uma vez; semeia a geração só se ainda desconhecida (não mascara troca feita noutra janela). */
  loadRoot: () => Promise<void>;
  /** Adota a raiz devolvida pelo PUT. */
  applyRoot: (root: NotebooksRoot) => void;
  setShortcutsOpen: (open: boolean) => void;
  setAboutOpen: (open: boolean) => void;
}

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  tabs: [],
  panel: null,
  railVisible: false,
  focusMode: false,
  rightPanel: null,
  root: null,
  shortcutsOpen: false,
  aboutOpen: false,

  ensureTab: (path) => {
    const existing = entries.get(path);
    if (existing) return existing;
    const notebook = createNotebookStore(path);
    const entry: NotebookEntry = { path, notebook, kernel: createKernelStore(notebook), view: { scrollTop: 0 } };
    entries.set(path, entry);
    set((s) => ({ tabs: [...s.tabs, path] }));
    void start(entry);
    return entry;
  },

  reload: (path) => {
    const entry = entries.get(path);
    if (!entry) return;
    entry.kernel.getState().close();
    entry.view.scrollTop = 0;
    void start(entry);
  },

  closeTab: (path) => {
    const entry = entries.get(path);
    if (!entry) return true;
    if (entry.notebook.getState().dirty && !window.confirm(UNSAVED_MESSAGE)) return false;
    const { tabs } = get();
    const i = tabs.indexOf(path);
    const rest = tabs.filter((p) => p !== path);
    // Fechando a aba ativa: ativa a vizinha (ou volta ao início).
    const { route } = useRouter.getState();
    if (route.view === "notebook" && route.path === path) {
      const next = rest[Math.min(i, rest.length - 1)];
      if (next) openNotebook(next, { replace: true });
      else openHome({ replace: true });
    }
    entries.delete(path);
    entry.kernel.getState().close();
    set({ tabs: rest });
    return true;
  },

  togglePanel: (panel) =>
    set((s) => {
      const next = s.panel === panel ? null : panel;
      return next ? { panel: next, railVisible: true, focusMode: false } : { panel: next };
    }),
  setPanel: (panel) =>
    set((s) =>
      panel !== null
        ? { panel, railVisible: true, focusMode: false }
        : { panel, railVisible: s.railVisible },
    ),
  toggleFocusMode: () => set((s) => ({ focusMode: !s.focusMode })),
  toggleRightPanel: (panel) =>
    set((s) => {
      // Em modo foco o painel aberto está oculto: o clique deve reexibi-lo, não fechá-lo.
      if (s.focusMode && s.rightPanel === panel) return { rightPanel: panel, focusMode: false };
      const next = s.rightPanel === panel ? null : panel;
      return next ? { rightPanel: next, focusMode: false } : { rightPanel: next };
    }),
  setRightPanel: (rightPanel) => set(rightPanel ? { rightPanel, focusMode: false } : { rightPanel }),
  loadRoot: async () => {
    if (get().root) return;
    const root = await getNotebooksRoot();
    if (getRootGeneration() === null) setRootGeneration(root.generation);
    set({ root });
  },
  applyRoot: (root) => set({ root }),
  setShortcutsOpen: (open) => set({ shortcutsOpen: open }),
  setAboutOpen: (open) => set({ aboutOpen: open }),
}));

/**
 * Fecha todas as abas (kernels incluídos), as com alterações primeiro; cada uma pede
 * confirmação via `closeTab`. Devolve `false` se o usuário cancelar (abas restantes ficam abertas).
 */
export function closeAllTabs(): boolean {
  const { tabs, closeTab } = useWorkspace.getState();
  const dirty = (p: string) => entries.get(p)?.notebook.getState().dirty === true;
  const ordered = [...tabs].sort((a, b) => Number(dirty(b)) - Number(dirty(a)));
  for (const path of ordered) if (!closeTab(path)) return false;
  return true;
}

/** Cria "Sem título N.ipynb" em `dir` e abre em nova aba. */
export async function createUntitledNotebook(dir: string): Promise<string> {
  const existing = await listDir(dir);
  const name = uniqueName(
    existing.map((e) => e.name),
    "Untitled",
    NOTEBOOK_EXT,
  );
  const path = joinPath(dir, name);
  await createEntry(path, "notebook");
  // A raiz e listagens em voo não são revalidadas pelo expandTo e podem
  // não conter o novo notebook; as demais pastas o expandTo já revalida.
  const tree = useNotebookTree.getState();
  if (dir === "" || tree.dirs[dir]?.status === "loading") void tree.reload(dir);
  tree.expandTo(dir);
  useWorkspace.getState().setPanel("notebooks");
  openNotebook(path);
  return path;
}

// Página: aviso de alterações não salvas e encerramento das sessões.
window.addEventListener("beforeunload", (e) => {
  for (const entry of entries.values()) {
    if (entry.notebook.getState().dirty) {
      e.preventDefault();
      e.returnValue = "";
      return;
    }
  }
});

window.addEventListener("pagehide", (e) => {
  if (e.persisted) return;
  for (const entry of entries.values()) entry.kernel.getState().close();
});
