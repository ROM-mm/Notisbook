/**
 * Controles do kernel na barra superior: seletor de ambiente (com o estado do
 * kernel), Run all, Interrupt, Restart kernel e menu ⋮ (Restart and run all).
 * Os notebooks abertos ficam na lista ao lado, no Banner. Usa as mesmas regras de habilitação do menu Run.
 */
import { useKernel, useKernelStore } from "../../state/notebookContext";
import { Menu, type MenuItem } from "../shell/Menu";
import { MoreVerticalIcon, PlayFilledIcon, RefreshIcon, StopFilledIcon } from "../shell/icons";
import { KernelSelector } from "./KernelSelector";
import { kernelAlive, kernelHasWork, kernelReady } from "./KernelStatus";
import styles from "./Kernel.module.css";

export function KernelToolbar() {
  const store = useKernelStore();
  const alive = useKernel(kernelAlive);
  const ready = useKernel(kernelReady);
  const hasWork = useKernel(kernelHasWork);
  const moreItems = (): MenuItem[] => [
    {
      label: "Restart and run all",
      disabled: !kernelReady(store.getState()),
      onSelect: () => store.getState().restartAndRunAll(),
      testId: "toolbar-restart-run-all",
    },
  ];
  return (
    <div className={styles.toolbar} role="toolbar" aria-label="Kernel controls" data-testid="kernel-toolbar">
      <KernelSelector />
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
        className={`${styles.toolBtn} ${styles.toolBtnStop}`}
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
        <RefreshIcon size={13} />
      </button>
      <Menu
        variant="icon"
        align="right"
        trigger={<MoreVerticalIcon size={14} />}
        ariaLabel="More kernel actions"
        title="More kernel actions"
        testId="toolbar-more"
        items={moreItems}
      />
    </div>
  );
}
