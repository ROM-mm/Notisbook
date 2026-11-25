/** Export do notebook: o estado em memória vai no corpo; o servidor só converte, sem tocar o disco. */
import type { Notebook } from "./nbformat";
import { requestBlob } from "./http";

export type ExportFormat = "ipynb" | "py" | "html";

/** Fontes de Settings › Appearance aplicadas ao HTML exportado (o backend valida; ausente → VT323/Roboto). */
export interface ExportFonts {
  code: string;
  markdown: string;
}

export async function exportNotebook(
  format: ExportFormat,
  notebook: Notebook,
  filename: string,
  fonts?: ExportFonts,
): Promise<{ blob: Blob; filename: string | null }> {
  return requestBlob(`/api/export/${format}`, { method: "POST", body: fonts ? { notebook, filename, fonts } : { notebook, filename } });
}
