/**
 * Controles do kernel na barra de abas: seletor de ambiente com estado,
 * Run all, Interrupt e menu ⋮ (Restart kernel, Restart and run all). Usa as
 * mesmas regras de habilitação do menu Run do header.
 */
import { useKernel, useKernelStore } from "../../state/notebookContext";
import { Menu, type MenuItem } from "../shell/Menu";
import { MoreVerticalIcon, PlayFilledIcon, StopFilledIcon } from "../shell/icons";
import { KernelSelector } from "./KernelSelector";
import { kernelAlive, kernelHasWork, kernelReady } from "./KernelStatus";
import styles from "./Kernel.module.css";

export function KernelToolbar() {
  const store = useKernelStore();
  const alive = useKernel(kernelAlive);
  const hasWork = useKernel(kernelHasWork);
  const moreItems = (): MenuItem[] => {
    const ready = kernelReady(store.getState());
    return [
      { label: "Restart kernel", disabled: !ready, onSelect: () => store.getState().restart(), testId: "toolbar-restart" },
      {
        label: "Restart and run all",
        disabled: !ready,
        onSelect: () => store.getState().restartAndRunAll(),
        testId: "toolbar-restart-run-all",
      },
    ];
  };
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
