/**
 * Seletor de ambiente na topbar, no lugar do "Python ▾" do Databricks.
 *
 * Combobox da aba ativa: lista os kernelspecs (`display_name`), marca o atual
 * e, ao escolher outro, chama `changeKernel(name)` da sessão desta aba (grava
 * `metadata.kernelspec` e recria a sessão no novo kernel). A lista é relida
 * de `GET /api/kernelspecs` a cada abertura (e por Settings após instalar ou
 * remover). O último item leva a Settings → Ambientes Spark.
 */
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { openSettings } from "../../state/router";
import { useKernel, useKernelStore, useNotebook } from "../../state/notebookContext";
import { refreshKernelspecs } from "../../state/workspace";
import menuStyles from "../shell/Menu.module.css";
import styles from "./Kernel.module.css";

const SWITCH_BUSY =
  "Cells are running or queued. Switching environments ends the current session (pending runs are discarded). Continue?";

export function KernelSelector() {
  const store = useKernelStore();
  const kernelName = useKernel((s) => s.kernelName);
  const kernelspecs = useKernel((s) => s.kernelspecs);
  const fromMetadata = useNotebook((s) => s.metadata.kernelspec?.display_name ?? null);
  const display = kernelspecs.find((k) => k.name === kernelName)?.display_name ?? fromMetadata ?? kernelName;

  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    void refreshKernelspecs().catch(() => undefined);
    (listRef.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]') ??
      listRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)"))?.focus();
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  };

  const choose = (name: string) => {
    close(true);
    const s = store.getState();
    if (name === s.kernelName && s.phase !== "error") return;
    const busy = s.running !== null || s.queue.length > 0;
    if (busy && !window.confirm(SWITCH_BUSY)) return;
    void s.changeKernel(name);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && open) {
      e.preventDefault();
      e.stopPropagation();
      close(true);
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    if (!open) {
      e.preventDefault();
      setOpen(true);
      return;
    }
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    if (buttons.length === 0) return;
    e.preventDefault();
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = e.key === "ArrowDown" ? (i + 1) % buttons.length : (i - 1 + buttons.length) % buttons.length;
    buttons[next]?.focus();
  };

  return (
    <div className={menuStyles.root} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.selector}
        data-testid="kernel-selector"
        data-kernel={kernelName ?? undefined}
        data-open={open || undefined}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Notebook environment (kernel)"
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.selectorLabel}>{display ?? "No kernel"}</span>
        <span aria-hidden="true" className={styles.selectorCaret}>
          ▾
        </span>
      </button>
      {open ? (
        <div ref={listRef} className={`${menuStyles.list} ${styles.selectorList}`} role="listbox" aria-label="Environments" data-testid="kernel-selector-list">
          {kernelspecs.length === 0 ? <div className={styles.selectorEmpty}>No environments installed.</div> : null}
          {kernelspecs.map((k) => {
            const current = k.name === kernelName;
            return (
              <button
                key={k.name}
                type="button"
                role="option"
                aria-selected={current}
                aria-checked={current}
                className={menuStyles.item}
                data-testid="kernel-option"
                data-kernel={k.name}
                onClick={() => choose(k.name)}
              >
                <span className={menuStyles.check} aria-hidden="true">
                  {current ? "✓" : ""}
                </span>
                <span className={menuStyles.label}>{k.display_name}</span>
                <span className={styles.selectorKernel}>{k.name}</span>
              </button>
            );
          })}
          <div className={menuStyles.separator} role="separator" />
          <button
            type="button"
            className={menuStyles.item}
            data-testid="kernel-manage"
            onClick={() => {
              close(false);
              openSettings();
            }}
          >
            <span className={menuStyles.check} aria-hidden="true" />
            <span className={menuStyles.label}>Manage environments…</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
