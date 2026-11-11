/**
 * Diálogo "Create Schema": valida o nome no cliente (mesma regra do backend e
 * duplicata sem diferenciar caixa contra os schemas já carregados) e mostra
 * no campo o erro devolvido pelo servidor.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createSchema, SCHEMA_NAME_PATTERN, schemaErrorMessage } from "../../api/catalog";
import dlg from "../../styles/dialog.module.css";
import styles from "./DataPanel.module.css";

interface Props {
  /** Nome real do catálogo (`spark_catalog`, `iceberg`). */
  catalog: string;
  /** Rótulo exibido do catálogo. */
  catalogLabel: string;
  /** Schemas existentes no catálogo, para a checagem de duplicata. */
  existing: string[];
  onCreated: () => void;
  onClose: () => void;
}

const FORMAT_HINT = "Use letters, digits and underscores, starting with a letter or underscore (max 128).";

export function CreateSchemaDialog({ catalog, catalogLabel, existing, onCreated, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const fieldId = useId();
  const [name, setName] = useState("");
  const [serverError, setServerError] = useState<{ forName: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  const trimmed = name.trim();
  let clientError: string | null = null;
  if (trimmed !== "") {
    if (!SCHEMA_NAME_PATTERN.test(trimmed)) clientError = FORMAT_HINT;
    else if (existing.some((s) => s.toLowerCase() === trimmed.toLowerCase())) clientError = "A schema with this name already exists.";
  }
  // O erro do servidor vale só para o nome que o provocou.
  const shownServerError = serverError && serverError.forName === trimmed ? serverError.text : null;
  const message = clientError ?? shownServerError;
  const canCreate = trimmed !== "" && clientError === null && !busy;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canCreate) return;
    setBusy(true);
    try {
      await createSchema(catalog, trimmed);
      onCreated();
      ref.current?.close();
    } catch (err) {
      setServerError({ forName: trimmed, text: schemaErrorMessage(err) });
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.confirmDialog}`}
      aria-labelledby={titleId}
      data-testid="create-schema-dialog"
      onClose={onClose}
      onCancel={(e) => busy && e.preventDefault()}
    >
      <form onSubmit={(e) => void submit(e)}>
        <div className={dlg.head}>
          <h2 id={titleId} className={dlg.title}>
            Create schema
          </h2>
          <button type="button" className="btn btn-ghost" aria-label="Close" disabled={busy} onClick={() => ref.current?.close()}>
            ✕
          </button>
        </div>
        <div className={styles.dialogBody}>
          <div className={styles.dialogField}>
            <label htmlFor={fieldId}>
              Schema name in <code>{catalogLabel}</code>
            </label>
            <input
              id={fieldId}
              className={`input ${message ? styles.dialogInvalid : ""}`}
              value={name}
              autoFocus
              spellCheck={false}
              autoComplete="off"
              aria-invalid={message ? true : undefined}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
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
          <button type="submit" className="btn btn-primary" disabled={!canCreate}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
