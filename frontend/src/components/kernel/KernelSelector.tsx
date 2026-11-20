/**
 * Seletor de ambiente na barra superior, unido ao estado do kernel: sem caixa
 * própria, mostra o ícone do runtime + versão e um quadradinho de estado
 * (verde livre, cinza ocupado/iniciando, vermelho erro); o estado por extenso
 * fica no `title`/`aria-label` do gatilho.
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
import sparkIconUrl from "../../../icons/spark.png";
import glueIconUrl from "../../../icons/glue.png";
import menuStyles from "../shell/Menu.module.css";
import { useKernelDescription } from "./KernelStatus";
import styles from "./Kernel.module.css";

const SWITCH_BUSY =
  "Cells are running or queued. Switching environments ends the current session (pending runs are discarded). Continue?";

type Runtime = "spark" | "glue" | "other";

/** Ícone por runtime: PNG em `frontend/icons/`; `null` (runtime "other") fica sem ícone. */
const RUNTIME_ICON_URL: Record<Runtime, string | null> = {
  spark: sparkIconUrl,
  glue: glueIconUrl,
  other: null,
};

/**
 * Tipo e versão do runtime derivados do `display_name`/`name` do kernelspec. A
 * versão é a logo após a palavra do runtime (ex.: "Spark 3.5.1"); sem ela, `null`.
 */
function runtimeOf(displayName: string, name: string | null): { runtime: Runtime; version: string | null } {
  const text = `${displayName} ${name ?? ""}`.toLowerCase();
  const runtime: Runtime = text.includes("glue") ? "glue" : text.includes("spark") ? "spark" : "other";
  const version = runtime !== "other" ? (displayName.match(/(?:spark|glue)\D*(\d+(?:\.\d+)+)/i)?.[1] ?? null) : null;
  return { runtime, version };
}

/** Ícone do runtime; sem ícone, `spacer` mantém a coluna vazia (alinhamento da lista). */
function RuntimeIcon({ runtime, spacer = false }: { runtime: Runtime; spacer?: boolean }) {
  const url = RUNTIME_ICON_URL[runtime];
  if (url) return <img className={styles.runtimeIcon} src={url} alt="" aria-hidden="true" />;
  return spacer ? <span className={styles.runtimeIcon} aria-hidden="true" /> : null;
}

/** Cor do quadradinho de estado do kernel (sem kernel, iniciando, ocupado ou reconectando: cinza). */
function stateMark(state: string): "free" | "busy" | "error" {
  if (state === "idle") return "free";
  if (state === "error" || state === "dead") return "error";
  return "busy";
}

export function KernelSelector() {
  const store = useKernelStore();
  const kernelName = useKernel((s) => s.kernelName);
  const kernelspecs = useKernel((s) => s.kernelspecs);
  const fromMetadata = useNotebook((s) => s.metadata.kernelspec?.display_name ?? null);
  const { label: stateLabel, state, error } = useKernelDescription();
  const display = kernelspecs.find((k) => k.name === kernelName)?.display_name ?? fromMetadata ?? kernelName;
  const { runtime, version } = runtimeOf(display ?? "", kernelName);
  const description = `Kernel: ${display ?? "No kernel"} — ${stateLabel.toLowerCase()}`;

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
        data-state={state}
        data-open={open || undefined}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={description}
        title={error ? `${description}\n${error}` : description}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.stateMark} data-mark={stateMark(state)} aria-hidden="true" />
        {display ? <RuntimeIcon runtime={runtime} /> : null}
        <span className={styles.selectorLabel}>{display ? (runtime !== "other" && version ? version : display) : "No kernel"}</span>
        <span aria-hidden="true" className={styles.selectorCaret}>
          ▾
        </span>
      </button>
      <span className={styles.srOnly} role="status" aria-live="polite">
        {stateLabel}
      </span>
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
                className={`${menuStyles.item} ${styles.selectorOption}`}
                data-testid="kernel-option"
                data-kernel={k.name}
                onClick={() => choose(k.name)}
              >
                <span className={menuStyles.check} aria-hidden="true">
                  {current ? "✓" : ""}
                </span>
                <RuntimeIcon runtime={runtimeOf(k.display_name, k.name).runtime} spacer />
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
