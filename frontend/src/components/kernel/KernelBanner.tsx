/**
 * Aviso no topo do notebook quando a sessão de kernel terminou sem volta
 * (sessão inexistente no servidor, substituída por outra aba, falha de
 * conexão): mostra o motivo e oferece reabrir o kernel (nova sessão).
 */
import { useKernel, useKernelStore } from "../../state/notebookContext";
import styles from "./Kernel.module.css";

export function KernelBanner() {
  const store = useKernelStore();
  const phase = useKernel((s) => s.phase);
  const error = useKernel((s) => s.error);
  const ended = useKernel((s) => s.ended);
  if (phase !== "error" || !error) return null;

  return (
    <div className={styles.banner} role="alert" data-testid="kernel-banner" data-reason={ended ?? "error"}>
      <span>{error}</span>
      <button type="button" className="btn" data-testid="kernel-reopen" onClick={() => void store.getState().open()}>
        Reopen kernel
      </button>
    </div>
  );
}
