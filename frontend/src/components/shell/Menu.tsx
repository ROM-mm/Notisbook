/**
 * Menu suspenso acessível e sem dependências (barra de menus do header e ⋮ da
 * célula). Os itens são calculados na abertura (`items()`), então refletem o
 * estado atual sem assinaturas extras. Fecha com clique fora, Esc ou ao
 * escolher um item; ↑/↓ navegam entre os itens habilitados.
 */
import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
import styles from "./Menu.module.css";

export type MenuItem =
  | {
      label: string;
      onSelect: () => void;
      disabled?: boolean;
      /** Dica de atalho à direita (ex.: "⌘S"). */
      shortcut?: string;
      /** Item de escolha (ex.: tema); `true` mostra a marca. */
      checked?: boolean;
      danger?: boolean;
      testId?: string;
    }
  | "separator";

export interface MenuProps {
  /** Conteúdo do botão (texto do menu ou ícone). */
  trigger: ReactNode;
  ariaLabel?: string;
  items: () => MenuItem[];
  testId?: string;
  /** "bar": item da barra de menus; "icon": botão de ícone (⋮). */
  variant?: "bar" | "icon";
  align?: "left" | "right";
  title?: string;
}

export function Menu({ trigger, ariaLabel, items, testId, variant = "bar", align = "left", title }: MenuProps) {
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
    // Foca o primeiro item habilitado ao abrir.
    listRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close(true);
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    if (buttons.length === 0) return;
    e.preventDefault();
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = e.key === "ArrowDown" ? (i + 1) % buttons.length : (i - 1 + buttons.length) % buttons.length;
    buttons[next]?.focus();
  };

  const list = open ? items() : [];

  return (
    <div className={styles.root} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className={variant === "bar" ? styles.barTrigger : styles.iconTrigger}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel}
        title={title}
        data-testid={testId}
        data-open={open || undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {trigger}
      </button>
      {open ? (
        <div ref={listRef} className={`${styles.list} ${align === "right" ? styles.right : ""}`} role="menu">
          {list.map((item, i) =>
            item === "separator" ? (
              <div key={`sep-${i}`} className={styles.separator} role="separator" />
            ) : (
              <button
                key={item.label}
                type="button"
                role={item.checked === undefined ? "menuitem" : "menuitemradio"}
                aria-checked={item.checked}
                className={item.danger ? `${styles.item} ${styles.danger}` : styles.item}
                disabled={item.disabled}
                data-testid={item.testId}
                onClick={() => {
                  close(false);
                  item.onSelect();
                }}
              >
                <span className={styles.check} aria-hidden="true">
                  {item.checked ? "✓" : ""}
                </span>
                <span className={styles.label}>{item.label}</span>
                {item.shortcut ? <kbd className={styles.shortcut}>{item.shortcut}</kbd> : null}
              </button>
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}
