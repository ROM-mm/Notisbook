/**
 * Contexto da aba de notebook: os componentes do notebook leem o store
 * do notebook e a sessão de kernel da SUA aba, sem depender de um singleton.
 *
 *   <NotebookProvider entry={entry}> … useNotebook(sel) / useKernel(sel) … </NotebookProvider>
 *
 * `useNotebookStore()` / `useKernelStore()` devolvem a instância (para
 * `getState()` em handlers).
 */
import { createContext, type ReactNode, useContext } from "react";
import { useStore } from "zustand";
import type { KernelSessionState, KernelStore } from "./kernel";
import type { NotebookState, NotebookStore } from "./notebook";
import type { NotebookEntry } from "./workspace";

const NotebookEntryContext = createContext<NotebookEntry | null>(null);

export function NotebookProvider({ entry, children }: { entry: NotebookEntry; children: ReactNode }) {
  return <NotebookEntryContext.Provider value={entry}>{children}</NotebookEntryContext.Provider>;
}

export function useNotebookEntry(): NotebookEntry {
  const entry = useContext(NotebookEntryContext);
  if (!entry) throw new Error("useNotebookEntry fora de <NotebookProvider>");
  return entry;
}

export function useNotebookStore(): NotebookStore {
  return useNotebookEntry().notebook;
}

export function useKernelStore(): KernelStore {
  return useNotebookEntry().kernel;
}

export function useNotebook<U>(selector: (s: NotebookState) => U): U {
  return useStore(useNotebookStore(), selector);
}

export function useKernel<U>(selector: (s: KernelSessionState) => U): U {
  return useStore(useKernelStore(), selector);
}
