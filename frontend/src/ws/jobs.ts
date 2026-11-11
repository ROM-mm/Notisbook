/**
 * Stream de eventos de job (`/api/jobs/{id}/events`). O servidor reenvia o log
 * acumulado a cada conexão, então `onReset` é chamado em toda (re)conexão para
 * o consumidor limpar o que já mostrou. Termina com `{phase:"done"}` + close 1000.
 */
import { encodePath } from "../api/http";
import { CloseCode, parseJobEvent, type JobEvent } from "./protocol";
import { type CloseInfo, JsonSocket } from "./socket";

export interface JobStreamHandlers {
  onReset?: () => void;
  onEvent?: (event: JobEvent) => void;
  /** `succeeded` derivado da linha final ("succeeded" | "failed: ..."). */
  onDone?: (succeeded: boolean, line: string) => void;
  /** Encerrou sem `done` (job inexistente, conexão recusada, desistência), com mensagem para a UI. */
  onAbort?: (info: CloseInfo, message: string) => void;
}

function abortMessage(info: CloseInfo): string {
  if (info.code === CloseCode.NotFound) return "the job no longer exists on the server";
  if (!info.opened) return "could not connect to the job stream (server is down or token/origin was refused)";
  return `connection lost (code ${info.code})`;
}

export class JobStream {
  private readonly socket: JsonSocket;
  private done = false;

  constructor(
    readonly jobId: string,
    handlers: JobStreamHandlers,
  ) {
    this.socket = new JsonSocket(
      `/api/jobs/${encodePath(jobId)}/events`,
      {
        onOpen: () => handlers.onReset?.(),
        onMessage: (raw) => {
          const ev = parseJobEvent(raw);
          if (!ev) return;
          if (ev.phase === "done") {
            this.done = true;
            handlers.onDone?.(ev.line === "succeeded", ev.line);
            return;
          }
          handlers.onEvent?.(ev);
        },
        onClose: (info) => {
          if (info.terminal && !this.done) handlers.onAbort?.(info, abortMessage(info));
        },
      },
      { maxAttempts: 5 },
    );
  }

  close(): void {
    this.socket.close();
  }
}
