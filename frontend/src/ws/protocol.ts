/** Protocolo WS v1 do canal de sessão (`/api/sessions/{id}/channel`) e do stream de jobs. */
import type { Output } from "../api/nbformat";
import type { JobLogLine, KernelState } from "../api/types";
import type { CellLanguage } from "../state/notebook";

export const PROTOCOL_VERSION = 1;

// Cliente → servidor
export type ClientFrame =
  | { v: 1; type: "execute"; cell_id: string; code: string; language?: CellLanguage }
  | { v: 1; type: "interrupt" }
  | { v: 1; type: "restart" };

// Servidor → cliente
export interface StatusFrame {
  v: 1;
  type: "status";
  state: KernelState;
}
export interface ExecuteInputFrame {
  v: 1;
  type: "execute_input";
  cell_id: string;
  execution_count: number;
}
export interface OutputFrame {
  v: 1;
  type: "output";
  cell_id: string;
  output: Output;
}
export interface ClearOutputFrame {
  v: 1;
  type: "clear_output";
  cell_id: string;
  wait: boolean;
}
export interface ExecuteReplyFrame {
  v: 1;
  type: "execute_reply";
  cell_id: string;
  status: "ok" | "error" | "aborted";
  execution_count: number | null;
}
export interface ErrorFrame {
  v: 1;
  type: "error";
  code: string;
  message: string;
}

export type ServerFrame =
  | StatusFrame
  | ExecuteInputFrame
  | OutputFrame
  | ClearOutputFrame
  | ExecuteReplyFrame
  | ErrorFrame;

const SERVER_TYPES: ReadonlySet<string> = new Set([
  "status",
  "execute_input",
  "output",
  "clear_output",
  "execute_reply",
  "error",
]);

/** Valida o envelope `{v:1, type}`; frames desconhecidos viram `null`. */
export function parseServerFrame(raw: unknown): ServerFrame | null {
  if (!raw || typeof raw !== "object") return null;
  const f = raw as { v?: unknown; type?: unknown };
  if (f.v !== PROTOCOL_VERSION || typeof f.type !== "string" || !SERVER_TYPES.has(f.type)) return null;
  return raw as ServerFrame;
}

/** Evento do stream de jobs; o último tem `phase: "done"`. */
export type JobEvent = JobLogLine;

export function parseJobEvent(raw: unknown): JobEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const e = raw as { phase?: unknown; line?: unknown };
  if (typeof e.phase !== "string" || typeof e.line !== "string") return null;
  return raw as JobEvent;
}

/** Códigos de fechamento relevantes. */
export const CloseCode = {
  Normal: 1000,
  NotFound: 4404, // sessão/job inexistente
  Replaced: 4409, // outra conexão assumiu a sessão
} as const;
