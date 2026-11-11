/**
 * Aba de notebook com kernel: liga a `NotebookView` à sessão de kernel
 * DA ABA (contexto `NotebookProvider`), aos renderizadores de saída e ao
 * rodapé por célula. A sessão é aberta/fechada pelo workspace
 * (`state/workspace.ts`), não pela montagem — trocar de aba não a encerra.
 */
import { useCallback } from "react";
import { cellLanguage, type EditorCell, type EditorCodeCell } from "../../state/notebook";
import { NotebookProvider } from "../../state/notebookContext";
import type { NotebookEntry } from "../../state/workspace";
import { NotebookView } from "../notebook/NotebookView";
import { OutputArea } from "../outputs/OutputArea";
import { CellRunFooter } from "./CellRunFooter";
import { KernelBanner } from "./KernelBanner";

const renderOutputs = (cell: EditorCodeCell) => <OutputArea outputs={cell.outputs} language={cellLanguage(cell)} />;
const renderFooter = (cell: EditorCell) => (cell.cell_type === "code" ? <CellRunFooter cellId={cell.id} /> : null);

export function NotebookPage({ entry }: { entry: NotebookEntry }) {
  const onRunCell = useCallback((id: string) => entry.kernel.getState().runCell(id), [entry]);
  return (
    <NotebookProvider entry={entry}>
      <NotebookView
        onRunCell={onRunCell}
        renderOutputs={renderOutputs}
        renderFooter={renderFooter}
        banner={<KernelBanner />}
      />
    </NotebookProvider>
  );
}
