/** Alternativa ao diálogo nativo: campo para colar um caminho absoluto, validado no backend. */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { listPath } from "../../api/files";
import { errorMessage } from "../../api/http";
import styles from "./DataPanel.module.css";

interface Props {
  initialPath: string | null;
  onSelect: (path: string) => void;
  onCancel: () => void;
}

export function DirectoryPicker({ initialPath, onSelect, onCancel }: Props) {
  const [typed, setTyped] = useState(initialPath ?? "");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Desmontar (ex.: Cancel) invalida a validação em voo: `onSelect` não pode disparar depois.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const p = typed.trim();
    if (!p.startsWith("/")) {
      setError("Enter an absolute path (starts with /).");
      return;
    }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setChecking(true);
    setError(null);
    try {
      const res = await listPath(p, 0, 1, ctrl.signal);
      if (ctrl.signal.aborted) return;
      onSelect(res.path);
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setError(errorMessage(err));
      setChecking(false);
    }
  }

  return (
    <form className={styles.picker} data-testid="files-picker" onSubmit={(e) => void submit(e)}>
      <div className={styles.pathForm}>
        <input
          className="input"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="/absolute/path"
          aria-label="Absolute path"
          spellCheck={false}
          autoFocus
        />
        <button type="submit" className="btn btn-primary" disabled={checking || typed.trim() === ""}>
          Use
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => {
            abortRef.current?.abort();
            onCancel();
          }}
        >
          Cancel
        </button>
      </div>
      {error ? (
        <p className={styles.notice} role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
