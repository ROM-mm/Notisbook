/**
 * Diálogo "Notislake connection": configura a conexão manual S3/MinIO, testa o
 * destino e volta ao modo automático. A secret key vive só no estado local do
 * corpo do diálogo, que é desmontado ao fechar; nunca vai ao store, a storage,
 * a log ou a mensagens (qualquer texto exibido passa por `redact`).
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError, errorMessage } from "../../api/http";
import {
  deleteNotislakeConfig,
  getNotislakeConfig,
  putNotislakeConfig,
  testNotislakeConnection,
  type NotislakeConfigDraft,
} from "../../api/notislake";
import { useNotislake } from "../../state/notislake";
import dlg from "../../styles/dialog.module.css";
import styles from "./DataPanel.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

const DEFAULT_REGION = "us-east-1";
const DEFAULT_TIMEOUT_S = "10";
const TIMEOUT_MIN = 1;
const TIMEOUT_MAX = 120;

interface Loaded {
  endpoint: string;
  accessKey: string;
  hasSecret: boolean;
  /** `manual` e `invalid` permitem voltar ao automático. */
  resettable: boolean;
}

type Feedback = { kind: "ok" | "error"; text: string } | null;

export function NotislakeConnectionDialog({ open, onClose }: Props) {
  // Desmontar o corpo descarta o segredo digitado.
  return open ? <DialogBody onClose={onClose} /> : null;
}

function DialogBody({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const titleId = useId();
  const ids = { name: useId(), endpoint: useId(), access: useId(), secret: useId(), region: useId(), timeout: useId() };

  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [region, setRegion] = useState(DEFAULT_REGION);
  const [timeoutS, setTimeoutS] = useState(DEFAULT_TIMEOUT_S);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | "reset" | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    nameRef.current?.focus();
    const controller = new AbortController();
    abortRef.current = controller;
    getNotislakeConfig(controller.signal)
      .then((cfg) => {
        if (cfg.mode === "manual") {
          setName(cfg.name);
          setEndpoint(cfg.endpoint);
          setAccessKey(cfg.access_key);
          setRegion(cfg.region);
          setTimeoutS(String(cfg.timeout_s));
          setLoaded({ endpoint: cfg.endpoint, accessKey: cfg.access_key, hasSecret: cfg.has_secret, resettable: true });
        } else {
          setLoaded({ endpoint: "", accessKey: "", hasSecret: false, resettable: cfg.mode === "invalid" });
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setLoadError(errorMessage(err));
        setLoaded({ endpoint: "", accessKey: "", hasSecret: false, resettable: false });
      });
    return () => controller.abort();
  }, []);

  /** Nenhum texto exibido pode conter o segredo digitado. */
  function redact(text: string): string {
    return secretKey === "" ? text : text.split(secretKey).join("***");
  }

  const ready = loaded !== null;
  const reusesSecret = secretKey === "" && loaded?.hasSecret === true;
  const identityChanged = loaded !== null && (endpoint.trim() !== loaded.endpoint || accessKey.trim() !== loaded.accessKey);
  const timeoutNumber = Number(timeoutS);
  const timeoutValid = timeoutS.trim() !== "" && Number.isFinite(timeoutNumber) && timeoutNumber >= TIMEOUT_MIN && timeoutNumber <= TIMEOUT_MAX;

  let invalidReason: string | null = null;
  if (name.trim() === "" || endpoint.trim() === "" || accessKey.trim() === "") invalidReason = "Name, endpoint and access key are required.";
  else if (!timeoutValid) invalidReason = `Timeout must be a number between ${TIMEOUT_MIN} and ${TIMEOUT_MAX} seconds.`;
  else if (!reusesSecret || identityChanged) {
    if (secretKey === "") invalidReason = "Secret key is required for a new endpoint or access key.";
  }

  const locked = !ready || busy !== null;
  const canSubmit = !locked && invalidReason === null;

  function draft(): NotislakeConfigDraft {
    const d: NotislakeConfigDraft = {
      name: name.trim(),
      endpoint: endpoint.trim(),
      access_key: accessKey.trim(),
      region: region.trim() || DEFAULT_REGION,
      timeout_s: timeoutNumber,
    };
    if (secretKey !== "") d.secret_key = secretKey;
    return d;
  }

  function fail(err: unknown): void {
    const code = err instanceof ApiError && err.code ? `${err.code}: ` : "";
    setFeedback({ kind: "error", text: redact(`${code}${errorMessage(err)}`) });
  }

  async function runTest() {
    if (!canSubmit) return;
    setBusy("test");
    setFeedback(null);
    try {
      const result = await testNotislakeConnection(draft(), abortRef.current?.signal);
      setFeedback(
        result.ok
          ? { kind: "ok", text: "Connection OK." }
          : { kind: "error", text: redact(`${result.code}: ${result.message}`) },
      );
    } catch (err) {
      fail(err);
    } finally {
      setBusy(null);
    }
  }

  function applied() {
    const store = useNotislake.getState();
    store.reset();
    store.refreshStatus(true);
    ref.current?.close();
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy("save");
    setFeedback(null);
    try {
      await putNotislakeConfig(draft());
      applied();
    } catch (err) {
      fail(err);
      setBusy(null);
    }
  }

  async function backToAutomatic() {
    if (locked) return;
    setBusy("reset");
    setFeedback(null);
    try {
      await deleteNotislakeConfig();
      applied();
    } catch (err) {
      fail(err);
      setBusy(null);
      setConfirmReset(false);
    }
  }

  const secretHint = loaded?.hasSecret
    ? "Leave empty to keep the saved secret. Required if the endpoint or access key changes."
    : "Stored by the server; never shown again.";

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.confirmDialog} ${styles.connectionDialog}`}
      aria-labelledby={titleId}
      data-testid="notislake-connection-dialog"
      onClose={onClose}
      onCancel={(e) => busy && e.preventDefault()}
    >
      <form onSubmit={(e) => void save(e)} autoComplete="off">
        <div className={dlg.head}>
          <h2 id={titleId} className={dlg.title}>
            Notislake connection
          </h2>
          <button type="button" className="btn btn-ghost" aria-label="Close" disabled={busy !== null} onClick={() => ref.current?.close()}>
            ✕
          </button>
        </div>
        <div className={styles.dialogBody}>
          <div className={styles.dialogField}>
            <label htmlFor={ids.name}>Name</label>
            <input id={ids.name} ref={nameRef} className="input" value={name} disabled={locked} spellCheck={false} autoComplete="off" onChange={(e) => setName(e.target.value)} />
          </div>
          <div className={styles.dialogField}>
            <label htmlFor={ids.endpoint}>Endpoint</label>
            <input id={ids.endpoint} className="input" value={endpoint} placeholder="https://minio.example.com:9000" disabled={locked} spellCheck={false} autoComplete="off" onChange={(e) => setEndpoint(e.target.value)} />
          </div>
          <div className={styles.dialogField}>
            <label htmlFor={ids.access}>Access key</label>
            <input id={ids.access} className="input" value={accessKey} disabled={locked} spellCheck={false} autoComplete="off" onChange={(e) => setAccessKey(e.target.value)} />
          </div>
          <div className={styles.dialogField}>
            <label htmlFor={ids.secret}>Secret key</label>
            <input
              id={ids.secret}
              className="input"
              type="password"
              value={secretKey}
              disabled={locked}
              spellCheck={false}
              autoComplete="off"
              aria-describedby={`${ids.secret}-hint`}
              onChange={(e) => setSecretKey(e.target.value)}
            />
            <span id={`${ids.secret}-hint`} className={styles.dialogHint}>
              {secretHint}
            </span>
          </div>
          <div className={styles.dialogFieldRow}>
            <div className={styles.dialogField}>
              <label htmlFor={ids.region}>Region</label>
              <input id={ids.region} className="input" value={region} disabled={locked} spellCheck={false} autoComplete="off" onChange={(e) => setRegion(e.target.value)} />
            </div>
            <div className={styles.dialogField}>
              <label htmlFor={ids.timeout}>Timeout (s)</label>
              <input id={ids.timeout} className="input" inputMode="numeric" value={timeoutS} disabled={locked} autoComplete="off" onChange={(e) => setTimeoutS(e.target.value)} />
            </div>
          </div>
          {loadError ? (
            <p className={styles.dialogError} role="alert">
              Could not load the current configuration: {loadError}
            </p>
          ) : null}
          {ready && invalidReason && (name !== "" || endpoint !== "" || accessKey !== "") ? <span className={styles.dialogHint}>{invalidReason}</span> : null}
          {feedback ? (
            <p className={feedback.kind === "ok" ? styles.dialogOk : styles.dialogError} role={feedback.kind === "ok" ? "status" : "alert"}>
              {feedback.text}
            </p>
          ) : null}
          {confirmReset ? (
            <p className={styles.dialogError} role="alert">
              Back to automatic removes the saved manual connection and returns to the local MinIO. Confirm?
            </p>
          ) : null}
        </div>
        <div className={dlg.foot}>
          {loaded?.resettable && !confirmReset ? (
            <button type="button" className={`btn ${styles.dialogFootStart}`} disabled={locked} onClick={() => setConfirmReset(true)}>
              Back to automatic
            </button>
          ) : null}
          {confirmReset ? (
            <>
              <button type="button" className={`btn ${styles.dialogFootStart}`} disabled={busy !== null} onClick={() => setConfirmReset(false)}>
                Keep manual
              </button>
              <button type="button" className={`btn ${styles.confirmDanger}`} disabled={busy !== null} onClick={() => void backToAutomatic()}>
                {busy === "reset" ? "Restoring…" : "Yes, back to automatic"}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn" disabled={busy !== null} onClick={() => ref.current?.close()}>
                Cancel
              </button>
              <button type="button" className="btn" disabled={!canSubmit} onClick={() => void runTest()}>
                {busy === "test" ? "Testing…" : "Test"}
              </button>
              <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
                {busy === "save" ? "Saving…" : "Save"}
              </button>
            </>
          )}
        </div>
      </form>
    </dialog>
  );
}
