/**
 * Diálogo modal de confirmação genérico (`<dialog>` + `showModal`). O pai
 * controla a vida do componente: monta para abrir e desmonta em `onCancel`.
 * Esc, ✕ e Cancelar chamam `onCancel`; durante `busy` nada fecha o diálogo.
 */
import { useEffect, useId, useRef, type ReactNode } from "react";
import dlg from "../../styles/dialog.module.css";
import styles from "../data/DataPanel.module.css";

export interface ConfirmDialogProps {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  /** Rótulo do botão de confirmação enquanto `busy`. */
  busyLabel?: string;
  /** Ação destrutiva: botão de confirmação em vermelho. */
  danger?: boolean;
  busy?: boolean;
  /** Impede confirmar sem ocupar o diálogo (ex.: prévia ainda carregando). */
  confirmDisabled?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  testId?: string;
}

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  busyLabel = "Working…",
  danger = false,
  busy = false,
  confirmDisabled = false,
  error = null,
  onConfirm,
  onCancel,
  testId,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.confirmDialog}`}
      aria-labelledby={titleId}
      data-testid={testId}
      onClose={onCancel}
      onCancel={(e) => busy && e.preventDefault()}
    >
      <div className={dlg.head}>
        <h2 id={titleId} className={dlg.title}>
          {title}
        </h2>
        <button type="button" className="btn btn-ghost" aria-label="Close" disabled={busy} onClick={() => ref.current?.close()}>
          ✕
        </button>
      </div>
      <div className={styles.dialogBody}>
        {children}
        {error ? (
          <p className={styles.dialogError} role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <div className={dlg.foot}>
        <button type="button" className="btn" disabled={busy} onClick={() => ref.current?.close()}>
          Cancel
        </button>
        <button
          type="button"
          className={`btn ${danger ? styles.confirmDanger : "btn-primary"}`}
          disabled={busy || confirmDisabled}
          onClick={onConfirm}
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
