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
 * remover).
 */
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useKernel, useKernelStore, useNotebook } from "../../state/notebookContext";
import { refreshKernelspecs } from "../../state/workspace";
import type { KernelRuntimeKind, Kernelspec } from "../../api/types";
import { DuckdbIcon, GlueIcon, SparkIcon, type TechIcon } from "../shell/techIcons";
import menuStyles from "../shell/Menu.module.css";
import { useKernelDescription } from "./KernelStatus";
import styles from "./Kernel.module.css";

const SWITCH_BUSY =
  "Cells are running or queued. Switching runtimes ends the current session (pending runs are discarded). Continue?";

/** Tipo do runtime para ícone/agrupamento; "other" = kernel sem `runtime_kind` reconhecível. */
type Runtime = KernelRuntimeKind | "other";

/**
 * Ícone por tipo de runtime (`shell/techIcons`); `null` ("other") fica sem ícone.
 * A ordem das chaves é a dos grupos na lista: Spark local, DuckDB, Docker e os demais.
 */
const RUNTIME_ICON: Record<Runtime, TechIcon | null> = {
  local: SparkIcon,
  duckdb: DuckdbIcon,
  docker: GlueIcon,
  other: null,
};

const GROUP_ORDER = Object.keys(RUNTIME_ICON) as Runtime[];

/**
 * Tipo e versão do runtime. O tipo vem do `runtime_kind` do kernelspec; sem spec (kernel
 * gravado no notebook e ainda não listado) ou em backend antigo, cai no texto do
 * `display_name`. A versão é o primeiro número com pontos do `display_name`
 * (ex.: "Spark 3.5.1"); sem ela, `null`.
 */
function runtimeOf(displayName: string, spec: Kernelspec | undefined): { runtime: Runtime; version: string | null } {
  const runtime: Runtime = spec?.runtime_kind ?? fallbackRuntime(displayName);
  const version = runtime !== "other" ? (displayName.match(/(\d+(?:\.\d+)+)/)?.[1] ?? null) : null;
  return { runtime, version };
}

/** Sem `runtime_kind`: Glue roda em Docker; Spark é local. Demais ficam "other". */
function fallbackRuntime(displayName: string): Runtime {
  const text = displayName.toLowerCase();
  if (text.includes("glue")) return "docker";
  if (text.includes("spark")) return "local";
  return "other";
}

/** Ícone do runtime; sem ícone, `spacer` mantém a coluna vazia (alinhamento da lista). */
function RuntimeIcon({ runtime, spacer = false }: { runtime: Runtime; spacer?: boolean }) {
  const Icon = RUNTIME_ICON[runtime];
  if (Icon) return <Icon className={styles.runtimeIcon} size={14} />;
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
  const currentSpec = kernelspecs.find((k) => k.name === kernelName);
  const display = currentSpec?.display_name ?? fromMetadata ?? kernelName;
  const { runtime, version } = runtimeOf(display ?? "", currentSpec);
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

  // Agrupa por tipo de runtime (ordem estável dentro do grupo); separador entre grupos.
  const grouped = GROUP_ORDER.map((g) => kernelspecs.filter((k) => runtimeOf(k.display_name, k).runtime === g)).filter((g) => g.length > 0);

  const seen = new Set<string>();
  const duplicatedNames = new Set<string>();
  for (const k of kernelspecs) {
    if (seen.has(k.display_name)) duplicatedNames.add(k.display_name);
    seen.add(k.display_name);
  }

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
        <div ref={listRef} className={`${menuStyles.list} ${styles.selectorList}`} role="listbox" aria-label="Runtimes" data-testid="kernel-selector-list">
          {kernelspecs.length === 0 ? <div className={styles.selectorEmpty}>No runtimes installed. Install one in Settings › Runtimes.</div> : null}
          {grouped.map((group, gi) => [
            gi > 0 ? <div key={`sep-${gi}`} className={menuStyles.separator} role="separator" /> : null,
            ...group.map((k) => {
              const current = k.name === kernelName;
              const ambiguous = duplicatedNames.has(k.display_name);
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
                  title={ambiguous ? `${k.display_name} (${k.name})` : k.display_name}
                  onClick={() => choose(k.name)}
                >
                  <span className={menuStyles.check} aria-hidden="true">
                    {current ? "✓" : ""}
                  </span>
                  <RuntimeIcon runtime={runtimeOf(k.display_name, k).runtime} spacer />
                  <span className={`${menuStyles.label} ${styles.selectorOptionLabel}`}>
                    <span className={styles.selectorOptionName}>{k.display_name}</span>
                    {ambiguous ? <span className={styles.selectorKernel}>{k.name}</span> : null}
                  </span>
                </button>
              );
            }),
          ])}
        </div>
      ) : null}
    </div>
  );
}
