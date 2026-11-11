import { useEffect, useRef, useState } from "react";
import { validateName } from "../../lib/paths";
import styles from "./FileBrowser.module.css";

export interface NameInputProps {
  initial: string;
  label: string;
  /** Resolve quando concluído; lança para manter o campo aberto com o erro. */
  onSubmit: (name: string) => Promise<void>;
  onCancel: () => void;
}

/** Campo inline de nome (criar/renomear): Enter confirma, Esc cancela. */
export function NameInput({ initial, label, onSubmit, onCancel }: NameInputProps) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    // Seleciona só o "stem" (sem extensão), como no Finder.
    const dot = initial.lastIndexOf(".");
    el.setSelectionRange(0, dot > 0 ? dot : initial.length);
  }, [initial]);

  async function submit() {
    if (busy) return;
    const name = value.trim();
    if (name === initial) {
      onCancel();
      return;
    }
    const invalid = validateName(name);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(name);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
      ref.current?.focus();
    }
  }

  return (
    <div className={styles.nameField}>
      <input
        ref={ref}
        className="input"
        aria-label={label}
        aria-invalid={error ? true : undefined}
        value={value}
        disabled={busy}
        onChange={(e) => {
          setValue(e.target.value);
          setError(null);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void submit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
        onBlur={() => {
          if (!busy && !error) onCancel();
        }}
      />
      {error ? (
        <span className={styles.nameError} role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
