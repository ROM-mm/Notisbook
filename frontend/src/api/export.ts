/** Export do notebook: o estado em memória vai no corpo; o servidor só converte, sem tocar o disco. */
import type { Notebook } from "./nbformat";
import { requestBlob } from "./http";

export type ExportFormat = "ipynb" | "py" | "html";

export async function exportNotebook(
  format: ExportFormat,
  notebook: Notebook,
  filename: string,
): Promise<{ blob: Blob; filename: string | null }> {
  return requestBlob(`/api/export/${format}`, { method: "POST", body: { notebook, filename } });
}
