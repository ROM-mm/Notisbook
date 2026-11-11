/** Cliente tipado do canal de sessão v1 (`/api/sessions/{id}/channel`). */
import { encodePath } from "../api/http";
import type { KernelState } from "../api/types";
import type { CellLanguage } from "../state/notebook";
import { type ClientFrame, CloseCode, parseServerFrame, type ServerFrame } from "./protocol";
import { type CloseInfo, type ConnectionState, JsonSocket } from "./socket";

/**
 * - `replaced`: 4409, outra conexão assumiu a sessão.
 * - `not_found`: 4404, a sessão não existe mais no servidor (sem reconexão).
 * - `closed`: 1000, fechamento normal.
 * - `connect_failed`: nenhuma tentativa chegou a abrir (servidor fora do ar ou
 *   handshake recusado com 403 por token/Origin/Host, que o navegador só vê como 1006).
 * - `gave_up`: a conexão caiu depois de aberta e as reconexões se esgotaram.
 */
export type SessionEndReason = "replaced" | "not_found" | "closed" | "connect_failed" | "gave_up";

export interface SessionChannelHandlers {
  /** Todo frame válido do servidor (inclui status, outputs, replies, erros). */
  onFrame?: (frame: ServerFrame) => void;
  onKernelState?: (state: KernelState) => void;
  onConnection?: (state: ConnectionState) => void;
  /**
   * Socket reaberto após uma queda. O servidor não reenvia saídas nem o
   * `execute_reply` de uma execução que estava em andamento; o próximo frame é
   * sempre `status` com o estado real do kernel.
   */
  onReconnected?: () => void;
  /** Conexão encerrada sem nova tentativa. */
  onEnd?: (reason: SessionEndReason, info: CloseInfo) => void;
}

function endReason(info: CloseInfo): SessionEndReason {
  switch (info.code) {
    case CloseCode.Replaced:
      return "replaced";
    case CloseCode.NotFound:
      return "not_found";
    case CloseCode.Normal:
      return "closed";
    default:
      return info.opened ? "gave_up" : "connect_failed";
  }
}

export class SessionChannel {
  private readonly socket: JsonSocket;

  constructor(
    readonly sessionId: string,
    handlers: SessionChannelHandlers,
  ) {
    this.socket = new JsonSocket(`/api/sessions/${encodePath(sessionId)}/channel`, {
      onState: (s) => handlers.onConnection?.(s),
      onOpen: (reconnected) => {
        if (reconnected) handlers.onReconnected?.();
      },
      onMessage: (raw) => {
        const frame = parseServerFrame(raw);
        if (!frame) return;
        if (frame.type === "status") handlers.onKernelState?.(frame.state);
        handlers.onFrame?.(frame);
      },
      onClose: (info) => {
        if (info.terminal) handlers.onEnd?.(endReason(info), info);
      },
    });
  }

  get connectionState(): ConnectionState {
    return this.socket.connectionState;
  }

  private sendFrame(frame: ClientFrame): boolean {
    return this.socket.send(frame);
  }

  /** `language` ausente = python (o backend assume python sem o campo). */
  execute(cellId: string, code: string, language?: CellLanguage): boolean {
    return this.sendFrame({ v: 1, type: "execute", cell_id: cellId, code, ...(language ? { language } : {}) });
  }

  interrupt(): boolean {
    return this.sendFrame({ v: 1, type: "interrupt" });
  }

  restart(): boolean {
    return this.sendFrame({ v: 1, type: "restart" });
  }

  close(): void {
    this.socket.close();
  }
}
