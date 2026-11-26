/**
 * Diálogo "Create bucket" do Notislake (mesmo cartão do `CreateSchemaDialog`). A regra do nome
 * fica no backend (fonte única); o cliente só antecipa a duplicata contra os buckets já listados.
 * Nome inválido (422) e bucket existente (409 `bucket_exists`) aparecem dentro do diálogo.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/http";
import { notislakeManageErrorMessage } from "../../api/notislake";
import { useNotislake } from "../../state/notislake";
import dlg from "../../styles/dialog.module.css";
import styles from "./DataPanel.module.css";

const NAME_HINT = "3–63 characters: lowercase letters, numbers, dots (.) and hyphens (-).";
const INVALID_NAME = `Invalid name. ${NAME_HINT}`;
const DUPLICATE = "A bucket with this name already exists.";

export function CreateBucketDialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const fieldId = useId();
  const hintId = useId();
  const buckets = useNotislake((s) => s.buckets);
  const [name, setName] = useState("");
  const [serverError, setServerError] = useState<{ forName: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    // showModal() move o foco para o primeiro focável (botão fechar); o foco no campo vem depois.
    inputRef.current?.focus();
  }, []);

  const trimmed = name.trim();
  const clientError = trimmed !== "" && buckets?.includes(trimmed) ? DUPLICATE : null;
  // O erro do servidor vale só para o nome que o provocou.
  const shownServerError = serverError && serverError.forName === trimmed ? serverError.text : null;
  const message = clientError ?? shownServerError;
  const canCreate = trimmed !== "" && message === null && !busy;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canCreate) return;
    setBusy(true);
    try {
      await useNotislake.getState().createBucket(trimmed);
      ref.current?.close();
    } catch (err) {
      const text = err instanceof ApiError && err.status === 422 ? INVALID_NAME : notislakeManageErrorMessage(err);
      setServerError({ forName: trimmed, text });
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.confirmDialog}`}
      aria-labelledby={titleId}
      data-testid="notislake-create-bucket"
      onClose={onClose}
      onCancel={(e) => busy && e.preventDefault()}
    >
      <form onSubmit={(e) => void submit(e)}>
        <div className={dlg.head}>
          <h2 id={titleId} className={dlg.title}>
            Create bucket
          </h2>
          <button type="button" className="btn btn-ghost" aria-label="Close" disabled={busy} onClick={() => ref.current?.close()}>
            ✕
          </button>
        </div>
        <div className={styles.dialogBody}>
          <div className={styles.dialogField}>
            <label htmlFor={fieldId}>Bucket name</label>
            <input
              id={fieldId}
              ref={inputRef}
              className={`input ${message ? styles.dialogInvalid : ""}`}
              value={name}
              spellCheck={false}
              autoComplete="off"
              aria-invalid={message ? true : undefined}
              aria-describedby={hintId}
              data-testid="notislake-create-bucket-name"
              onChange={(e) => setName(e.target.value)}
            />
            <span id={hintId} className={styles.dialogHint}>
              {NAME_HINT}
            </span>
          </div>
          <p className={styles.dialogHint}>
            Creates <code>landing/</code>, <code>bronze/</code>, <code>silver/</code>, <code>gold/</code>.
          </p>
          {message ? (
            <p className={styles.dialogError} role="alert">
              {message}
            </p>
          ) : null}
        </div>
        <div className={dlg.foot}>
          <button type="button" className="btn" disabled={busy} onClick={() => ref.current?.close()}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!canCreate} data-testid="notislake-create-bucket-submit">
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
