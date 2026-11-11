/**
 * Indicador compacto do estado da sessão de kernel da aba (topbar).
 * As ações (executar tudo, interromper, reiniciar…) ficam na `KernelToolbar`
 * e no menu Run da topbar.
 */
import { type KernelSessionState } from "../../state/kernel";
import { useKernel } from "../../state/notebookContext";
import styles from "./Kernel.module.css";

type Tone = "ok" | "busy" | "warn" | "danger" | "muted";

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

export function KernelStatus() {
  const phase = useKernel((s) => s.phase);
  const kernelState = useKernel((s) => s.kernelState);
  const connection = useKernel((s) => s.connection);
  const error = useKernel((s) => s.error);
  const { label, tone, state } = describe({ phase, kernelState, connection });

  return (
    <span className={styles.status} data-testid="kernel-status" data-state={state} title={error ?? undefined} role="status">
      <span className={`${styles.dot} ${styles[tone]}`} aria-hidden="true" />
      {label}
    </span>
  );
}
