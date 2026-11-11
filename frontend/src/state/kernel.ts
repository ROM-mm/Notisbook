/**
 * Sessão de kernel de UM notebook (zustand vanilla) + fila de execução.
 * Uma instância por aba, criada com `createKernelStore(notebookStore)` e
 * registrada em `state/workspace.ts` junto ao store do notebook; os
 * componentes leem a instância da aba via contexto (`useKernel`).
 *
 * Ciclo de vida (dirigido pelo workspace): quando o notebook termina de
 * carregar, `open()` lista os kernelspecs, usa `metadata.kernelspec.name`
 * (ou o primeiro kernelspec disponível, gravado com `setKernelspec`), cria a
 * sessão (`POST /api/sessions`) e conecta o `SessionChannel`. Ao fechar a aba
 * do notebook (ou a página), `close()` fecha o canal e faz
 * `DELETE /api/sessions/{id}`.
 *
 * Execução: uma célula por vez. `runCell`/`runAll`/`runFrom` enfileiram; a
 * fila envia o próximo `execute` só após o `execute_reply` do anterior, então
 * a duração (envio → reply, medida aqui) é só da célula. `clear_output`,
 * `output`, `execute_input` e `execute_reply` atualizam o store do notebook.
 * Um reply `error`/`aborted` descarta as pendentes do mesmo "executar tudo".
 *
 * Queda do canal: o servidor não reenvia saídas nem o `execute_reply` da
 * execução em andamento, e o primeiro frame após reconectar é `status` com o
 * estado real. A célula em andamento termina `aborted` (com nota no rodapé) e a
 * fila só volta a andar depois desse `status`; se o kernel ainda estiver `busy`
 * terminando a célula órfã, espera o próximo `idle` antes do próximo `execute`.
 *
 * Pontos de extensão:
 * - Seletor de ambiente: `kernelspecs`, `kernelName` e `changeKernel(name)`
 *   (grava o kernelspec no notebook e troca a sessão).
 * - Barra de status: `phase`, `kernelState`, `connection`, `error`,
 *   `running`/`queue` e `runs` (status/duração por célula).
 */
import { createStore, type StoreApi } from "zustand/vanilla";
import { errorMessage } from "../api/http";
import { createSession, deleteSession, listKernelspecs } from "../api/kernels";
import type { Kernelspec, KernelState } from "../api/types";
import type { ServerFrame } from "../ws/protocol";
import { SessionChannel, type SessionEndReason } from "../ws/session";
import type { ConnectionState } from "../ws/socket";
import { cellLanguage, type NotebookStore } from "./notebook";

/** Estado da sessão do ponto de vista da UI. */
export type SessionPhase = "none" | "starting" | "ready" | "error";
export type CellRunStatus = "queued" | "running" | "ok" | "error" | "aborted";

export interface CellRun {
  status: CellRunStatus;
  executionCount: number | null;
  /** `performance.now()` no envio do `execute` (null enquanto na fila). */
  startedAt: number | null;
  /** Envio → `execute_reply`, em ms (null até terminar). */
  durationMs: number | null;
  /** Epoch ms do término (para "às HH:MM"). */
  finishedAt: number | null;
  /** Observação exibida no rodapé (ex.: resultado perdido na queda da conexão). */
  note: string | null;
}

export interface QueueItem {
  cellId: string;
  /** Lote de "executar tudo/abaixo"; null para execução avulsa. */
  batch: number | null;
}

export interface KernelSessionState {
  path: string | null;
  sessionId: string | null;
  kernelName: string | null;
  kernelspecs: Kernelspec[];
  phase: SessionPhase;
  kernelState: KernelState | null;
  connection: ConnectionState | null;
  /** Último erro (sessão, canal ou frame `error` do servidor). */
  error: string | null;
  /** Motivo do encerramento definitivo do canal (null enquanto ativo). */
  ended: SessionEndReason | null;
  runs: Record<string, CellRun>;
  queue: QueueItem[];
  running: QueueItem | null;

  /** Abre a sessão para o notebook (já carregado) desta instância. */
  open: () => Promise<void>;
  close: () => void;
  /** Troca o kernel do notebook (metadata + nova sessão). */
  changeKernel: (name: string) => Promise<void>;
  runCell: (cellId: string) => void;
  runAll: () => void;
  runFrom: (cellId: string) => void;
  interrupt: () => void;
  restart: () => void;
  restartAndRunAll: () => void;
  dismissError: () => void;
}

/** Formato do rodapé: segundos com 2 casas (`0.05 s`, `1.02 s`). */
export function formatDuration(ms: number): string {
  return `${(Math.max(0, ms) / 1000).toFixed(2)} s`;
}

const INITIAL = {
  path: null as string | null,
  sessionId: null,
  kernelName: null,
  kernelspecs: [] as Kernelspec[],
  phase: "none" as SessionPhase,
  kernelState: null,
  connection: null,
  error: null,
  ended: null as SessionEndReason | null,
  runs: {} as Record<string, CellRun>,
  queue: [] as QueueItem[],
  running: null,
};

const END_MESSAGES: Record<SessionEndReason, string> = {
  replaced: "This notebook was opened in another tab; the kernel connection moved there.",
  not_found:
    "The kernel session no longer exists on the server (it may have been restarted). Reopen the kernel to continue; previous variables and state were lost.",
  closed: "Kernel connection closed.",
  connect_failed:
    "Could not connect to the kernel: server is down or the connection was refused (token/origin). Reload the page using the link with the token.",
  gave_up: "Could not reconnect to the kernel.",
};

const LOST_ON_RECONNECT = "The connection dropped during execution; the result could not be recovered.";

export type KernelStore = StoreApi<KernelSessionState>;

function now(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export function createKernelStore(notebook: NotebookStore): KernelStore {
  const path = notebook.getState().path;
  return createStore<KernelSessionState>((set, get) => {
    // Estado não reativo (por instância).
    let channel: SessionChannel | null = null;
    /** Invalida continuações assíncronas de um `open`/`changeKernel` anterior. */
    let token = 0;
    let batchSeq = 0;
    /** Células com `clear_output(wait=true)`: limpar ao chegar a próxima saída. */
    const pendingClear = new Set<string>();
    /** Reiniciar e executar tudo: aguardando `restarting` → `idle`. */
    let runAllAfterRestart: "none" | "await_restart" | "await_idle" = "none";
    /** Canal caiu: a fila espera o primeiro `status` da nova conexão. */
    let awaitingStatus = false;
    /** Após reconectar com o kernel `busy` (célula órfã terminando): só envia no próximo `idle`. */
    let holdUntilIdle = false;
    /**
     * Execução abortada na queda do canal: se o `execute_reply` dela ainda chegar
     * pela nova conexão, não pode encerrar uma nova execução da mesma célula.
     */
    let staleReply: { cellId: string; executionCount: number | null } | null = null;

    const codeCellIds = (fromId?: string): string[] => {
      const cells = notebook.getState().cells;
      const start = fromId ? Math.max(0, cells.findIndex((c) => c.id === fromId)) : 0;
      return cells.slice(start).filter((c) => c.cell_type === "code").map((c) => c.id);
    };

    const setRun = (id: string, patch: Partial<CellRun>) =>
      set((s) => {
        const prev: CellRun = s.runs[id] ?? {
          status: "queued",
          executionCount: null,
          startedAt: null,
          durationMs: null,
          finishedAt: null,
          note: null,
        };
        return { runs: { ...s.runs, [id]: { ...prev, ...patch } } };
      });

    const dropRuns = (ids: string[]) =>
      set((s) => {
        if (ids.length === 0) return s;
        const runs = { ...s.runs };
        for (const id of ids) delete runs[id];
        return { runs };
      });

    /** Remove da fila (e do rodapé) os itens que casam com `pred`. */
    const discardQueued = (pred: (item: QueueItem) => boolean) => {
      const { queue } = get();
      const dropped = queue.filter(pred);
      if (dropped.length === 0) return;
      set({ queue: queue.filter((q) => !pred(q)) });
      dropRuns(dropped.map((q) => q.cellId).filter((id) => get().running?.cellId !== id));
    };

    /**
     * Fim da execução em andamento (reply recebido ou abortada localmente).
     * `keepBatch` preserva as pendentes do mesmo lote mesmo sem `ok`: usado quando
     * o resultado se perdeu na queda do canal, sem indicar falha da célula.
     */
    const finish = (
      status: "ok" | "error" | "aborted",
      executionCount: number | null,
      opts: { note?: string; keepBatch?: boolean } = {},
    ) => {
      const item = get().running;
      if (!item) return;
      const run = get().runs[item.cellId];
      const durationMs = run?.startedAt != null ? now() - run.startedAt : null;
      if (executionCount !== null) notebook.getState().setExecutionCount(item.cellId, executionCount);
      setRun(item.cellId, {
        status,
        durationMs,
        finishedAt: Date.now(),
        executionCount: executionCount ?? run?.executionCount ?? null,
        note: opts.note ?? null,
      });
      pendingClear.delete(item.cellId);
      set({ running: null });
      if (status !== "ok" && !opts.keepBatch && item.batch !== null) discardQueued((q) => q.batch === item.batch);
    };

    /** Envia o próximo da fila se nada estiver rodando e o kernel aceitar. */
    const pump = () => {
      for (;;) {
        const s = get();
        if (s.running || s.queue.length === 0 || !channel) return;
        if (s.kernelState !== "idle" && s.kernelState !== "busy") return;
        if (awaitingStatus || (holdUntilIdle && s.kernelState !== "idle")) return;
        if (channel.connectionState !== "open") return;
        const [item, ...rest] = s.queue;
        if (!item) return;
        const nb = notebook.getState();
        const cell = nb.cells.find((c) => c.id === item.cellId);
        if (!cell || cell.cell_type !== "code") {
          set({ queue: rest });
          dropRuns([item.cellId]);
          continue;
        }
        nb.clearOutputs(cell.id);
        nb.setExecutionCount(cell.id, null);
        pendingClear.delete(cell.id);
        const startedAt = now();
        const language = cellLanguage(cell);
        // python segue sem o campo (default do backend).
        if (!channel.execute(cell.id, cell.source, language !== "python" ? language : undefined)) return; // fica na fila até reconectar
        set({ queue: rest, running: item });
        setRun(cell.id, { status: "running", startedAt, durationMs: null, finishedAt: null, executionCount: null, note: null });
        return;
      }
    };

    const enqueue = (ids: string[], batch: number | null) => {
      const nb = notebook.getState();
      const queued = new Set(get().queue.map((q) => q.cellId));
      const add: QueueItem[] = [];
      for (const id of ids) {
        if (queued.has(id)) continue;
        const cell = nb.cells.find((c) => c.id === id);
        if (!cell || cell.cell_type !== "code") continue;
        if (!cell.source.trim()) {
          // Célula vazia: como no Jupyter, limpa sem executar.
          nb.clearOutputs(id);
          nb.setExecutionCount(id, null);
          if (get().running?.cellId !== id) dropRuns([id]);
          continue;
        }
        add.push({ cellId: id, batch });
        queued.add(id);
      }
      if (add.length === 0) return;
      set((s) => ({ queue: [...s.queue, ...add] }));
      for (const item of add) {
        if (get().running?.cellId === item.cellId) continue;
        setRun(item.cellId, { status: "queued", startedAt: null, durationMs: null, finishedAt: null, note: null });
      }
      pump();
    };

    /**
     * Encerra tudo o que estava pendente (restart, kernel morto, sessão encerrada).
     * Também esquece o reply atrasado: depois de restart/morte ele pode nunca
     * chegar e a contagem do kernel recomeça, então um `execution_count` guardado
     * descartaria o reply legítimo de uma nova execução da mesma célula.
     */
    const abortAll = () => {
      finish("aborted", null);
      discardQueued(() => true);
      pendingClear.clear();
      staleReply = null;
    };

    const onFrame = (frame: ServerFrame) => {
      const nb = notebook.getState();
      switch (frame.type) {
        case "execute_input":
          nb.setExecutionCount(frame.cell_id, frame.execution_count);
          if (get().running?.cellId === frame.cell_id) setRun(frame.cell_id, { executionCount: frame.execution_count });
          break;
        case "clear_output":
          if (frame.wait) pendingClear.add(frame.cell_id);
          else {
            pendingClear.delete(frame.cell_id);
            nb.clearOutputs(frame.cell_id);
          }
          break;
        case "output":
          if (pendingClear.delete(frame.cell_id)) nb.clearOutputs(frame.cell_id);
          nb.appendOutput(frame.cell_id, frame.output);
          break;
        case "execute_reply":
          if (isStaleReply(frame.cell_id, frame.execution_count)) break;
          if (get().running?.cellId === frame.cell_id) {
            finish(frame.status, frame.execution_count);
            pump();
          }
          break;
        case "error":
          set({ error: frame.message || frame.code });
          break;
        case "status":
          break; // tratado em onKernelState
      }
    };

    /** Execução em andamento cujo resultado se perdeu na queda do canal. */
    const abortLostRun = () => {
      const item = get().running;
      if (!item) return;
      staleReply = { cellId: item.cellId, executionCount: get().runs[item.cellId]?.executionCount ?? null };
      finish("aborted", null, { note: LOST_ON_RECONNECT, keepBatch: true });
    };

    /**
     * Reply atrasado da execução abortada: casa pelo `execution_count` dela; se
     * ele não chegou antes da queda, por diferir do da execução atual.
     */
    const isStaleReply = (cellId: string, executionCount: number | null): boolean => {
      if (!staleReply || staleReply.cellId !== cellId) return false;
      const stale =
        staleReply.executionCount !== null
          ? executionCount === staleReply.executionCount
          : executionCount !== get().runs[cellId]?.executionCount;
      if (stale) staleReply = null;
      return stale;
    };

    const onKernelState = (state: KernelState) => {
      set({ kernelState: state });
      if (awaitingStatus) {
        awaitingStatus = false;
        abortLostRun();
        holdUntilIdle = state !== "idle";
      }
      if (state === "idle") holdUntilIdle = false;
      if (state === "restarting" || state === "dead") {
        abortAll();
        if (state === "restarting" && runAllAfterRestart === "await_restart") runAllAfterRestart = "await_idle";
        if (state === "dead") runAllAfterRestart = "none";
        return;
      }
      if (state === "idle" && runAllAfterRestart === "await_idle") {
        runAllAfterRestart = "none";
        get().runAll();
        return;
      }
      pump();
    };

    /** Fecha canal e sessão atuais (sem mexer no restante do estado). */
    const teardown = () => {
      abortAll();
      runAllAfterRestart = "none";
      awaitingStatus = false;
      holdUntilIdle = false;
      channel?.close();
      channel = null;
      const id = get().sessionId;
      if (id) void deleteSession(id, { keepalive: true }).catch(() => undefined);
      set({ sessionId: null, kernelState: null, connection: null });
    };

    const startSession = async (myToken: number, path: string, kernelName: string) => {
      set({ kernelName, phase: "starting", kernelState: "starting", error: null, ended: null });
      const { session_id } = await createSession(path, kernelName);
      if (myToken !== token) {
        // open/close mais recente venceu: não deixa kernel órfão.
        void deleteSession(session_id).catch(() => undefined);
        return;
      }
      const ch: SessionChannel = new SessionChannel(session_id, {
        onConnection: (c) => {
          if (channel !== ch) return;
          if (c === "reconnecting") awaitingStatus = true;
          set({ connection: c });
          if (c === "open") pump();
        },
        onReconnected: () => channel === ch && abortLostRun(),
        onKernelState: (k) => channel === ch && onKernelState(k),
        onFrame: (f) => channel === ch && onFrame(f),
        onEnd: (reason) => {
          if (channel !== ch) return;
          abortAll();
          set({ phase: "error", connection: "closed", ended: reason, error: END_MESSAGES[reason] });
        },
      });
      channel = ch;
      set({ sessionId: session_id, phase: "ready", connection: ch.connectionState });
    };

    return {
      ...INITIAL,
      path,

      open: async () => {
        const myToken = ++token;
        teardown();
        set({ ...INITIAL, path, phase: "starting" });
        try {
          const specs = await listKernelspecs();
          if (myToken !== token) return;
          set({ kernelspecs: specs });
          let name = notebook.getState().metadata.kernelspec?.name;
          if (!name) {
            const first = specs[0];
            if (!first) throw new Error("No kernel available. Install a Spark environment.");
            notebook.getState().setKernelspec(first.name, first.display_name, first.language);
            name = first.name;
          }
          await startSession(myToken, path, name);
        } catch (err) {
          if (myToken !== token) return;
          set({ phase: "error", kernelState: null, error: errorMessage(err) });
        }
      },

      close: () => {
        token += 1;
        teardown();
        set({ ...INITIAL, path });
      },

      changeKernel: async (name) => {
        const { kernelspecs } = get();
        const spec = kernelspecs.find((k) => k.name === name);
        if (!spec) {
          set({ error: `Unknown kernel: ${name}` });
          return;
        }
        const myToken = ++token;
        teardown();
        notebook.getState().setKernelspec(spec.name, spec.display_name, spec.language);
        set({ runs: {}, queue: [], running: null });
        try {
          await startSession(myToken, path, spec.name);
        } catch (err) {
          if (myToken !== token) return;
          set({ phase: "error", kernelState: null, error: errorMessage(err) });
        }
      },

      runCell: (cellId) => enqueue([cellId], null),
      runAll: () => enqueue(codeCellIds(), ++batchSeq),
      runFrom: (cellId) => enqueue(codeCellIds(cellId), ++batchSeq),

      interrupt: () => {
        if (!channel) return;
        discardQueued(() => true);
        channel.interrupt();
      },

      restart: () => {
        if (!channel) return;
        discardQueued(() => true);
        runAllAfterRestart = "none";
        channel.restart();
      },

      restartAndRunAll: () => {
        if (!channel) return;
        discardQueued(() => true);
        if (channel.restart()) runAllAfterRestart = "await_restart";
      },

      dismissError: () => set({ error: null }),
    };
  });
}
