/**
 * Barra de execução do notebook (fixa no topo das células): Run all,
 * Interrupt e Restart kernel. Assina o kernel da aba e usa as mesmas regras
 * de habilitação do menu Run da topbar.
 */
import { useKernel, useKernelStore } from "../../state/notebookContext";
import { PlayFilledIcon, RefreshIcon, StopFilledIcon } from "../shell/icons";
import { kernelAlive, kernelHasWork, kernelReady } from "./KernelStatus";
import styles from "./Kernel.module.css";

export function KernelToolbar() {
  const store = useKernelStore();
  const alive = useKernel(kernelAlive);
  const ready = useKernel(kernelReady);
  const hasWork = useKernel(kernelHasWork);
  return (
    <div className={styles.toolbar} role="toolbar" aria-label="Kernel controls" data-testid="kernel-toolbar">
      <button
        type="button"
        className={`${styles.toolBtn} ${styles.toolBtnPrimary}`}
        data-testid="toolbar-run-all"
        title="Run all cells"
        aria-label="Run all cells"
        disabled={!alive}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => store.getState().runAll()}
      >
        <PlayFilledIcon size={12} />
      </button>
      <button
        type="button"
        className={styles.toolBtn}
        data-testid="toolbar-interrupt"
        title="Interrupt kernel"
        aria-label="Interrupt kernel"
        disabled={!alive || !hasWork}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => store.getState().interrupt()}
      >
        <StopFilledIcon size={12} />
      </button>
      <button
        type="button"
        className={styles.toolBtn}
        data-testid="toolbar-restart"
        title="Restart kernel"
        aria-label="Restart kernel"
        disabled={!ready}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => store.getState().restart()}
      >
        <RefreshIcon size={14} />
      </button>
    </div>
  );
}
