/**
 * Modal aninhado "Add libraries": linhas nome | versão (opcional, vazio = latest).
 * Nome repetido (normalizado como no PyPI) bloqueia o Add; erros 422 do backend voltam para a linha.
 */
import { useEffect, useRef, useState } from "react";
import { errorMessage } from "../../api/http";
import type { RequirementRow } from "../../api/types";
import { rowErrors } from "./usePackages";
import dlg from "../../styles/dialog.module.css";
import styles from "./Spark.module.css";

interface Row {
  id: number;
  name: string;
  spec: string;
}

interface Props {
  onSubmit: (rows: RequirementRow[]) => Promise<void>;
  onClose: () => void;
}

const MAX_ROWS = 50;
const normalize = (name: string) => name.trim().toLowerCase().replace(/[-_.]+/g, "-");

export function AddLibraryDialog({ onSubmit, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const nextId = useRef(1);
  const [rows, setRows] = useState<Row[]>([{ id: 0, name: "", spec: "" }]);
  const [serverErrors, setServerErrors] = useState<Map<number, string>>(new Map());
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  const seen = new Set<string>();
  const duplicate = new Map<number, string>();
  for (const r of rows) {
    const k = normalize(r.name);
    if (!k) continue;
    if (seen.has(k)) duplicate.set(r.id, `"${r.name.trim()}" is already in the list.`);
    seen.add(k);
  }
  const filled = rows.filter((r) => r.name.trim() !== "");
  const canAdd = filled.length > 0 && duplicate.size === 0 && !busy;

  const patch = (id: number, change: Partial<Row>) => {
    setRows((list) => list.map((r) => (r.id === id ? { ...r, ...change } : r)));
    setServerErrors((m) => {
      if (!m.has(id)) return m;
      const copy = new Map(m);
      copy.delete(id);
      return copy;
    });
  };

  const submit = async () => {
    setBusy(true);
    setFormError(null);
    setServerErrors(new Map());
    try {
      await onSubmit(filled.map((r) => ({ name: r.name.trim(), spec: r.spec.trim() })));
      ref.current?.close();
    } catch (err) {
      const errors = rowErrors(err);
      if (errors) {
        const map = new Map<number, string>();
        for (const e of errors) {
          const row = filled[e.index];
          if (row) map.set(row.id, e.message);
        }
        setServerErrors(map);
      } else {
        setFormError(errorMessage(err));
      }
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.addDialog}`}
      aria-labelledby="add-lib-title"
      data-testid="spark-add-dialog"
      onClose={onClose}
      onCancel={(e) => busy && e.preventDefault()}
    >
      <div className={dlg.head}>
        <h2 id="add-lib-title" className={dlg.title}>
          Add libraries
        </h2>
        <button type="button" className="btn btn-ghost" aria-label="Close" disabled={busy} onClick={() => ref.current?.close()}>
          ✕
        </button>
      </div>
      <div className={styles.addBody}>
        <div className={styles.addGrid}>
          <span className={styles.colLabel}>Library (PyPI)</span>
          <span className={styles.colLabel}>Version (optional)</span>
          <span />
          {rows.map((r, i) => {
            const message = duplicate.get(r.id) ?? serverErrors.get(r.id);
            return (
              <div key={r.id} className={styles.addRow}>
                <input
                  className={`${styles.input} ${message ? styles.inputBad : ""}`}
                  value={r.name}
                  aria-label={`Library ${i + 1}`}
                  aria-invalid={message ? true : undefined}
                  autoFocus={i === rows.length - 1 && rows.length > 1}
                  spellCheck={false}
                  autoComplete="off"
                  onChange={(e) => patch(r.id, { name: e.target.value })}
                />
                <input
                  className={styles.input}
                  value={r.spec}
                  placeholder="latest"
                  aria-label={`Version ${i + 1}`}
                  spellCheck={false}
                  autoComplete="off"
                  onChange={(e) => patch(r.id, { spec: e.target.value })}
                />
                <button
                  type="button"
                  className="btn btn-ghost"
                  aria-label={`Remove row ${i + 1}`}
                  disabled={rows.length === 1}
                  onClick={() => setRows((list) => list.filter((x) => x.id !== r.id))}
                >
                  −
                </button>
                {message ? <p className={styles.fieldError}>{message}</p> : null}
              </div>
            );
          })}
        </div>
        <button
          type="button"
          className={`btn btn-ghost ${styles.addRowBtn}`}
          disabled={rows.length >= MAX_ROWS}
          onClick={() => setRows((list) => [...list, { id: nextId.current++, name: "", spec: "" }])}
        >
          + Add row
        </button>
        <p className={styles.text}>
          Empty version installs the latest release. If a library is already installed, it will be updated to the given version.
        </p>
        {formError ? <p className={styles.error}>{formError}</p> : null}
      </div>
      <div className={dlg.foot}>
        <button type="button" className="btn" disabled={busy} onClick={() => ref.current?.close()}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" disabled={!canAdd} onClick={() => void submit()}>
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
    </dialog>
  );
}
