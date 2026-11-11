/**
 * Menu de contexto posicionado no cursor (portal em `document.body`). Fecha com
 * Esc, clique fora, scroll, resize ou ao escolher um item; ↑/↓/Home/End navegam
 * entre os itens habilitados. Ao fechar, devolve o foco a `returnFocusTo`.
 */
import {
  type KeyboardEvent,
  useLayoutEffect,
  useEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import type { MenuItem } from "./Menu";
import styles from "./Menu.module.css";

export interface ContextMenuProps {
  x: number;
  y: number;
  items: MenuItem[];
  ariaLabel: string;
  onClose: () => void;
  returnFocusTo?: HTMLElement | null;
}

const VIEWPORT_MARGIN = 4;

export function ContextMenu({
  x,
  y,
  items,
  ariaLabel,
  onClose,
  returnFocusTo,
}: ContextMenuProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });

  // Mantém o menu dentro da viewport (mede após o primeiro render).
  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setPos({
      left: Math.max(
        VIEWPORT_MARGIN,
        Math.min(x, window.innerWidth - width - VIEWPORT_MARGIN),
      ),
      top: Math.max(
        VIEWPORT_MARGIN,
        Math.min(y, window.innerHeight - height - VIEWPORT_MARGIN),
      ),
    });
  }, [x, y]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
      ?.focus();
    const onDown = (e: MouseEvent) => {
      if (!listRef.current?.contains(e.target as Node)) onClose();
    };
    // Captura: o scroll não propaga, e o contêiner rolável é qualquer ancestral.
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onClose, true);
    window.addEventListener("resize", onClose);
    window.addEventListener("blur", onClose);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onClose, true);
      window.removeEventListener("resize", onClose);
      window.removeEventListener("blur", onClose);
    };
  }, [onClose]);

  useEffect(() => () => returnFocusTo?.focus(), [returnFocusTo]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    const buttons = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
      ) ?? [],
    );
    if (buttons.length === 0) return;
    e.preventDefault();
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next = 0;
    if (e.key === "ArrowDown") next = (i + 1) % buttons.length;
    else if (e.key === "ArrowUp")
      next = (i - 1 + buttons.length) % buttons.length;
    else if (e.key === "End") next = buttons.length - 1;
    buttons[next]?.focus();
  };

  return createPortal(
    <div
      ref={listRef}
      className={styles.list}
      style={{ position: "fixed", left: pos.left, top: pos.top, right: "auto" }}
      role="menu"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((item, i) =>
        item === "separator" ? (
          <div key={`sep-${i}`} className={styles.separator} role="separator" />
        ) : (
          <button
            key={item.label}
            type="button"
            role="menuitem"
            className={
              item.danger ? `${styles.item} ${styles.danger}` : styles.item
            }
            disabled={item.disabled}
            data-testid={item.testId}
            onClick={() => {
              onClose();
              item.onSelect();
            }}
          >
            <span className={styles.check} aria-hidden="true" />
            <span className={styles.label}>{item.label}</span>
            {item.shortcut ? (
              <kbd className={styles.shortcut}>{item.shortcut}</kbd>
            ) : null}
          </button>
        ),
      )}
    </div>,
    document.body,
  );
}
