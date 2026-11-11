/** Tipos mínimos do nbformat v4 usados pela UI. */

/** Texto multilinha do nbformat: string única ou lista de linhas. */
export type MultilineString = string | string[];

export type MimeBundle = Record<string, unknown>;

export interface StreamOutput {
  output_type: "stream";
  name: "stdout" | "stderr";
  text: MultilineString;
}

export interface DisplayDataOutput {
  output_type: "display_data";
  data: MimeBundle;
  metadata?: Record<string, unknown>;
  transient?: Record<string, unknown>;
}

export interface ExecuteResultOutput {
  output_type: "execute_result";
  execution_count: number | null;
  data: MimeBundle;
  metadata?: Record<string, unknown>;
}

export interface ErrorOutput {
  output_type: "error";
  ename: string;
  evalue: string;
  traceback: string[];
}

export type Output = StreamOutput | DisplayDataOutput | ExecuteResultOutput | ErrorOutput;

interface BaseCell {
  id?: string;
  source: MultilineString;
  metadata: Record<string, unknown>;
}

export interface CodeCell extends BaseCell {
  cell_type: "code";
  execution_count: number | null;
  outputs: Output[];
}

export interface MarkdownCell extends BaseCell {
  cell_type: "markdown";
  attachments?: Record<string, MimeBundle>;
}

export interface RawCell extends BaseCell {
  cell_type: "raw";
  attachments?: Record<string, MimeBundle>;
}

export type Cell = CodeCell | MarkdownCell | RawCell;

export interface KernelspecMetadata {
  name: string;
  display_name: string;
  language?: string;
}

export interface NotebookMetadata {
  kernelspec?: KernelspecMetadata;
  language_info?: { name: string; [key: string]: unknown };
  [key: string]: unknown;
}

export interface Notebook {
  nbformat: 4;
  nbformat_minor: number;
  metadata: NotebookMetadata;
  cells: Cell[];
}

/** Junta um MultilineString em uma única string. */
export function joinMultiline(text: MultilineString): string {
  return Array.isArray(text) ? text.join("") : text;
}
