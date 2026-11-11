/**
 * Estado da sessão de kernel da aba e predicados de habilitação das ações.
 * O indicador visual (ponto + palavra de estado) vive no `KernelSelector`;
 * as ações ficam na `KernelToolbar` e no menu Run do header.
 */
import { type KernelSessionState } from "../../state/kernel";
import { useKernel } from "../../state/notebookContext";

export type Tone = "ok" | "busy" | "warn" | "danger" | "muted";

function describe(s: Pick<KernelSessionState, "phase" | "kernelState" | "connection">): {
  label: string;
  tone: Tone;
  state: string;
} {
  if (s.phase === "none") return { label: "No kernel", tone: "muted", state: "none" };
  if (s.phase === "error") return { label: "Kernel error", tone: "danger", state: "error" };
  if (s.connection === "reconnecting") return { label: "Reconnecting…", tone: "warn", state: "reconnecting" };
  switch (s.kernelState) {
    case "idle":
      return { label: "Idle", tone: "ok", state: "idle" };
    case "busy":
      return { label: "Running", tone: "busy", state: "busy" };
    case "restarting":
      return { label: "Restarting…", tone: "warn", state: "restarting" };
    case "dead":
      return { label: "Kernel dead", tone: "danger", state: "dead" };
    case "starting":
    case null:
      return { label: "Starting…", tone: "warn", state: "starting" };
  }
}

/** Kernel aceita execução (sessão pronta, canal aberto, idle/busy). */
export function kernelAlive(s: Pick<KernelSessionState, "phase" | "connection" | "kernelState">): boolean {
  return s.phase === "ready" && s.connection === "open" && (s.kernelState === "idle" || s.kernelState === "busy");
}

/** Sessão pronta, canal aberto e kernel fora de restart (habilita restart/ações do menu Run). */
export function kernelReady(s: Pick<KernelSessionState, "phase" | "connection" | "kernelState">): boolean {
  return s.phase === "ready" && s.connection === "open" && s.kernelState !== "restarting";
}

/** Há execução em curso ou enfileirada (habilita interrupt). */
export function kernelHasWork(s: Pick<KernelSessionState, "running" | "queue" | "kernelState">): boolean {
  return s.running !== null || s.queue.length > 0 || s.kernelState === "busy";
}

/** Descrição (rótulo, tom e estado) da sessão de kernel da aba, reativa ao store. */
export function useKernelDescription(): { label: string; tone: Tone; state: string; error: string | null } {
  const phase = useKernel((s) => s.phase);
  const kernelState = useKernel((s) => s.kernelState);
  const connection = useKernel((s) => s.connection);
  const error = useKernel((s) => s.error);
  return { ...describe({ phase, kernelState, connection }), error };
}
