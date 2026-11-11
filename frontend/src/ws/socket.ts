/**
 * WebSocket JSON com reconexão simples (backoff exponencial limitado).
 * Não reconecta em fechamentos terminais: 1000 (normal), 4404 (sessão/job
 * inexistente, enviado pelo servidor logo após aceitar o handshake) e 4409
 * (substituída por outra conexão).
 *
 * Token/Origin/Host inválidos fazem o servidor recusar o handshake com HTTP 403;
 * o navegador não expõe esse status e entrega só um close 1006 sem nunca abrir.
 * Por isso 1006 segue o fluxo normal de reconexão e, esgotadas as tentativas,
 * `CloseInfo.opened` diz se o socket chegou a abrir alguma vez (falha de
 * conexão/autenticação desde o início) ou se a conexão caiu depois.
 */
import { CloseCode } from "./protocol";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface CloseInfo {
  code: number;
  reason: string;
  /** true quando não haverá nova tentativa. */
  terminal: boolean;
  /** true se alguma conexão deste socket chegou a abrir. */
  opened: boolean;
}

export interface JsonSocketHandlers {
  onOpen?: (reconnected: boolean) => void;
  onMessage?: (data: unknown) => void;
  onState?: (state: ConnectionState) => void;
  onClose?: (info: CloseInfo) => void;
}

export interface JsonSocketOptions {
  maxAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Códigos adicionais tratados como terminais. */
  terminalCodes?: number[];
}

const DEFAULT_TERMINAL = [CloseCode.Normal, CloseCode.NotFound, CloseCode.Replaced];

/** URL ws(s):// na mesma origem da página (proxy do Vite em dev, FastAPI em produção). */
export function wsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

export class JsonSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private everOpened = false;
  private state: ConnectionState = "connecting";
  private readonly terminal: Set<number>;
  private readonly maxAttempts: number;
  private readonly baseDelay: number;
  private readonly maxDelay: number;

  constructor(
    private readonly path: string,
    private readonly handlers: JsonSocketHandlers,
    opts: JsonSocketOptions = {},
  ) {
    this.terminal = new Set([...DEFAULT_TERMINAL, ...(opts.terminalCodes ?? [])]);
    this.maxAttempts = opts.maxAttempts ?? 8;
    this.baseDelay = opts.baseDelayMs ?? 500;
    this.maxDelay = opts.maxDelayMs ?? 10_000;
    this.connect();
  }

  get connectionState(): ConnectionState {
    return this.state;
  }

  /** Envia um objeto JSON; devolve false se o socket não estiver aberto. */
  send(data: unknown): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(data));
    return true;
  }

  /** Fecha definitivamente (sem reconexão). */
  close(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close(CloseCode.Normal);
    this.setState("closed");
  }

  private setState(s: ConnectionState): void {
    if (this.state === s) return;
    this.state = s;
    this.handlers.onState?.(s);
  }

  private connect(): void {
    if (this.stopped) return;
    const ws = new WebSocket(wsUrl(this.path));
    this.ws = ws;
    ws.onopen = () => {
      const reconnected = this.everOpened;
      this.everOpened = true;
      this.attempts = 0;
      this.setState("open");
      this.handlers.onOpen?.(reconnected);
    };
    ws.onmessage = (ev: MessageEvent) => {
      if (typeof ev.data !== "string") return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(ev.data);
      } catch {
        return;
      }
      this.handlers.onMessage?.(parsed);
    };
    ws.onclose = (ev: CloseEvent) => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (this.stopped) return;
      // Handshake recusado (403) ou servidor fora do ar chegam como 1006: contam
      // como tentativa e desistimos ao atingir o limite.
      const terminal = this.terminal.has(ev.code) || this.attempts >= this.maxAttempts;
      this.handlers.onClose?.({ code: ev.code, reason: ev.reason, terminal, opened: this.everOpened });
      if (terminal) {
        this.stopped = true;
        this.setState("closed");
        return;
      }
      this.setState("reconnecting");
      const delay = Math.min(this.maxDelay, this.baseDelay * 2 ** this.attempts);
      this.attempts += 1;
      this.timer = setTimeout(() => {
        this.timer = null;
        this.connect();
      }, delay);
    };
  }
}
