/**
 * Combo único de runtimes (Settings → Runtimes → Install): combobox "select-only" do
 * WAI-ARIA com listbox agrupado, no estilo dos dropdowns do app (`shell/Menu.module.css`).
 *
 * - Grupos fixos, nesta ordem: Data processing (Spark local), Analytics (DuckDB) e Docker (Glue).
 * - Cada item mostra rótulo, descrição (data/imagem), estado (✓ installed, installing…,
 *   Docker unavailable) e o selo de formatos quando o bundle traz Delta, Iceberg e Hudi.
 *   Itens não instaláveis ficam desabilitados (`aria-disabled`).
 * - Teclado: setas, Home/End, Enter, Esc, Tab fecha; com a lista fechada, digitar faz
 *   type-ahead pelo rótulo. O campo de filtro (aberto por clique/Enter/Alt+↓) filtra a lista.
 * - Selecionar só marca a escolha (`onChange`); quem instala é o botão Install do painel.
 */
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { DuckdbIcon, GlueIcon, SparkIcon, type TechIcon } from "../shell/techIcons";
import menuStyles from "../shell/Menu.module.css";
import styles from "./RuntimeCombo.module.css";

export type RuntimeCategory = "processing" | "analytics" | "docker";

/** Categorias na ordem de exibição, com título e ícone do grupo. */
export const RUNTIME_CATEGORIES: { key: RuntimeCategory; title: string; Icon: TechIcon }[] = [
  { key: "processing", title: "Data processing", Icon: SparkIcon },
  { key: "analytics", title: "Analytics", Icon: DuckdbIcon },
  { key: "docker", title: "Docker", Icon: GlueIcon },
];

const CATEGORY = Object.fromEntries(RUNTIME_CATEGORIES.map((c) => [c.key, c])) as Record<RuntimeCategory, (typeof RUNTIME_CATEGORIES)[number]>;

export type RuntimeOptionState = "installed" | "installing" | "unavailable";

export interface RuntimeOption {
  /** Identificador estável (`spark:3.5.10`, `duckdb:2.0.1`, `docker:glue-5.0`). */
  id: string;
  category: RuntimeCategory;
  label: string;
  /** Data de lançamento, imagem ou outro detalhe curto. */
  description?: string | null;
  state?: RuntimeOptionState | null;
  /** Formatos de tabela do bundle; com delta, iceberg e hudi mostra o selo "Complete". */
  formats?: string[] | null;
  /** Não selecionável (instalado, instalando ou indisponível). */
  disabled: boolean;
}

const STATE_TEXT: Record<RuntimeOptionState, string> = {
  installed: "✓ installed",
  installing: "installing…",
  unavailable: "Docker unavailable",
};

const COMPLETE_FORMATS = ["delta", "iceberg", "hudi"];
const COMPLETE_BADGE = "Complete · Delta · Iceberg · Hudi";

export const isComplete = (formats: string[] | null | undefined) =>
  !!formats && COMPLETE_FORMATS.every((f) => formats.map((x) => x.toLowerCase()).includes(f));

/** Janela do type-ahead: teclas dentro dela formam um prefixo só. */
const TYPEAHEAD_MS = 600;

interface Props {
  options: RuntimeOption[];
  /** `id` da opção escolhida; `null` sem escolha. */
  value: string | null;
  /** Só registra a escolha; não instala nada. */
  onChange: (id: string) => void;
  disabled?: boolean;
  placeholder?: string;
  label?: string;
}

export function RuntimeCombo({ options, value, onChange, disabled = false, placeholder = "Choose a runtime…", label = "Runtime to install" }: Props) {
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (id: string) => `${baseId}-opt-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const typeahead = useRef<{ text: string; at: number }>({ text: "", at: 0 });

  const selected = options.find((o) => o.id === value) ?? null;

  /** Opções visíveis (filtro aplicado), já na ordem dos grupos. */
  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const match = (o: RuntimeOption) => !q || `${o.label} ${o.description ?? ""} ${CATEGORY[o.category].title}`.toLowerCase().includes(q);
    return RUNTIME_CATEGORIES.flatMap((c) => options.filter((o) => o.category === c.key && match(o)));
  }, [options, filter]);
  const enabled = visible.filter((o) => !o.disabled);

  // Fecha ao clicar fora.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Mantém o item ativo visível na lista rolável.
  useEffect(() => {
    if (!open || !active) return;
    document.getElementById(optionId(active))?.scrollIntoView({ block: "nearest" });
    // optionId é derivado de baseId (estável).
  }, [open, active]);

  // O ativo sumiu do filtro: vai para o primeiro habilitado visível.
  useEffect(() => {
    if (open && active && !enabled.some((o) => o.id === active)) setActive(enabled[0]?.id ?? null);
  }, [open, active, enabled]);

  const openList = (focusFilter: boolean, initial?: string | null) => {
    if (disabled) return;
    setFilter("");
    setActive(initial !== undefined ? initial : selected && !selected.disabled ? selected.id : (options.find((o) => !o.disabled)?.id ?? null));
    setOpen(true);
    if (focusFilter) window.setTimeout(() => filterRef.current?.focus(), 0);
  };

  const close = (refocus: boolean) => {
    setOpen(false);
    setFilter("");
    if (refocus) triggerRef.current?.focus();
  };

  const choose = (o: RuntimeOption) => {
    if (o.disabled) return;
    onChange(o.id);
    close(true);
  };

  const move = (delta: 1 | -1) => {
    if (enabled.length === 0) return;
    const i = enabled.findIndex((o) => o.id === active);
    const next = i < 0 ? (delta === 1 ? 0 : enabled.length - 1) : (i + delta + enabled.length) % enabled.length;
    setActive(enabled[next]?.id ?? null);
  };

  /** Type-ahead: acumula as teclas digitadas em sequência e vai à próxima opção com esse prefixo. */
  const typeAhead = (key: string) => {
    const now = Date.now();
    const t = typeahead.current;
    t.text = now - t.at > TYPEAHEAD_MS ? key : t.text + key;
    t.at = now;
    const pool = options.filter((o) => !o.disabled);
    const ordered = RUNTIME_CATEGORIES.flatMap((c) => pool.filter((o) => o.category === c.key));
    const start = Math.max(0, ordered.findIndex((o) => o.id === active));
    const rotated = [...ordered.slice(start + (t.text.length === 1 ? 1 : 0)), ...ordered.slice(0, start + (t.text.length === 1 ? 1 : 0))];
    const hit = rotated.find((o) => o.label.toLowerCase().startsWith(t.text.toLowerCase()));
    if (!hit) return;
    if (open) setActive(hit.id);
    else openList(false, hit.id);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    const inFilter = e.currentTarget === filterRef.current;
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openList(true);
        return;
      }
      if (e.key === "Home" || e.key === "End") {
        e.preventDefault();
        const pool = RUNTIME_CATEGORIES.flatMap((c) => options.filter((o) => o.category === c.key && !o.disabled));
        openList(false, (e.key === "Home" ? pool[0] : pool[pool.length - 1])?.id ?? null);
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && e.key !== " ") typeAhead(e.key);
      return;
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        move(1);
        return;
      case "ArrowUp":
        e.preventDefault();
        if (e.altKey) {
          const o = enabled.find((x) => x.id === active);
          if (o) choose(o);
          else close(true);
        } else move(-1);
        return;
      case "Home":
      case "End":
        // No filtro, Home/End movem o cursor do texto; fora dele, vão ao primeiro/último item.
        if (inFilter && filter) return;
        e.preventDefault();
        setActive((e.key === "Home" ? enabled[0] : enabled[enabled.length - 1])?.id ?? null);
        return;
      case "Enter": {
        e.preventDefault();
        const o = enabled.find((x) => x.id === active);
        if (o) choose(o);
        return;
      }
      case "Escape":
        e.preventDefault();
        e.stopPropagation();
        close(true);
        return;
      case "Tab":
        close(false);
        return;
      default:
        // Fora do filtro (aberto por type-ahead), letras seguem o type-ahead.
        if (!inFilter && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          if (e.key === " ") {
            e.preventDefault();
            const o = enabled.find((x) => x.id === active);
            if (o) choose(o);
            return;
          }
          typeAhead(e.key);
        }
    }
  };

  const activeDescendant = open && active ? optionId(active) : undefined;
  const SelectedIcon = selected ? CATEGORY[selected.category].Icon : null;

  return (
    <div className={styles.combo} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        className={styles.trigger}
        data-testid="runtime-combo"
        data-open={open || undefined}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={activeDescendant}
        disabled={disabled}
        onClick={() => (open ? close(false) : openList(true))}
        onKeyDown={onKeyDown}
      >
        <span className={styles.icon} aria-hidden="true">
          {SelectedIcon ? <SelectedIcon size={14} /> : null}
        </span>
        <span className={selected ? styles.triggerLabel : `${styles.triggerLabel} ${styles.placeholder}`}>{selected ? selected.label : placeholder}</span>
        <span className={styles.triggerTag}>{selected ? CATEGORY[selected.category].title : ""}</span>
        <span className={styles.caret} aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <div className={`${menuStyles.list} ${styles.popup}`}>
          <input
            ref={filterRef}
            className={styles.filter}
            type="search"
            placeholder="Filter…"
            aria-label="Filter runtimes"
            aria-controls={listId}
            aria-activedescendant={activeDescendant}
            aria-autocomplete="list"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <div ref={listRef} id={listId} role="listbox" aria-label={label} className={styles.listbox} data-testid="runtime-combo-list">
            {visible.length === 0 ? <div className={styles.empty}>No runtimes match.</div> : null}
            {RUNTIME_CATEGORIES.map((c) => {
              const items = visible.filter((o) => o.category === c.key);
              if (items.length === 0) return null;
              const installed = options.filter((o) => o.category === c.key && o.state === "installed").length;
              const headId = `${baseId}-grp-${c.key}`;
              return (
                <div key={c.key} role="group" aria-labelledby={headId} data-category={c.key}>
                  <div id={headId} className={styles.group} role="presentation">
                    <span className={styles.icon} aria-hidden="true">
                      <c.Icon size={14} />
                    </span>
                    <span>{c.title}</span>
                    <span className={styles.groupCount}>{installed > 0 ? `${installed} installed` : ""}</span>
                  </div>
                  {items.map((o) => {
                    const isSelected = o.id === value;
                    return (
                      <div
                        key={o.id}
                        id={optionId(o.id)}
                        role="option"
                        aria-selected={isSelected}
                        aria-disabled={o.disabled || undefined}
                        className={styles.option}
                        data-active={o.id === active || undefined}
                        data-testid="runtime-combo-option"
                        data-option={o.id}
                        onMouseDown={(e) => e.preventDefault()}
                        onMouseMove={() => !o.disabled && o.id !== active && setActive(o.id)}
                        onClick={() => choose(o)}
                      >
                        <span className={menuStyles.check} aria-hidden="true">
                          {isSelected ? "✓" : ""}
                        </span>
                        <span className={styles.optionLabel}>{o.label}</span>
                        <span className={styles.optionDesc}>
                          {o.description}
                          {isComplete(o.formats) ? <span className={styles.badge}>{COMPLETE_BADGE}</span> : null}
                        </span>
                        <span className={styles.optionState} data-state={o.state ?? undefined}>
                          {o.state ? STATE_TEXT[o.state] : ""}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Rótulo de categoria com ícone (lista Installed). */
export function CategoryTag({ category }: { category: RuntimeCategory }) {
  const { title, Icon } = CATEGORY[category];
  return (
    <span className={styles.category} data-category={category}>
      <Icon size={12} />
      {title}
    </span>
  );
}
