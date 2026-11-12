/**
 * Layout raiz em coluna: header (nome, tagline, menus e toggles) e abas de
 * notebooks (com os controles do kernel) em largura total, abaixo delas uma
 * linha com a lateral esquerda (⌘B), o conteúdo e a lateral direita (⌥⌘B) e,
 * no rodapé, a barra de atalhos (só exibição; os atalhos vivem nos listeners).
 *
 * Pontos de extensão:
 * - `entry`: aba ativa (ou null), repassada ao header e à barra de abas
 *   (seletor de ambiente em `components/kernel/KernelSelector.tsx`).
 * - Laterais: `Explorer` empilha os cartões de uma lateral; a composição e a
 *   ordem vêm de `state/layout.ts` (LEFT_CARDS/RIGHT_CARDS) e os cartões
 *   concretos são mapeados em `Explorer.tsx`.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { DEFAULT_RIGHT_PANEL_WIDTH, DEFAULT_SIDE_PANEL_WIDTH, useLayout } from "../../state/layout";
import { type NotebookEntry, useWorkspace } from "../../state/workspace";
import styles from "./AppShell.module.css";
import { Banner } from "./Banner";
import { Explorer } from "./Explorer";
import { ResizeHandle } from "./ResizeHandle";
import { AboutDialog } from "./AboutDialog";
import { SHORTCUTS, ShortcutsDialog } from "./ShortcutsDialog";
import { SidePanel } from "./SidePanel";
import { TabBar } from "./TabBar";

const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);

// Atalhos do rodapé: seleção declarada (pelo texto de tecla) dentro de SHORTCUTS.
const FOOTER_KEYS = ["Shift+Enter", "⌘S / Ctrl+S", "Esc", "⌘. / Ctrl+.", "⌘B / Ctrl+B", "⌥⌘B / Ctrl+Alt+B"];
const FOOTER_SHORTCUTS = FOOTER_KEYS.map((k) => {
  const found = SHORTCUTS.find(([keys]) => keys === k);
  if (!found && import.meta.env.DEV) console.warn(`Atalho do rodapé ausente em SHORTCUTS: ${k}`);
  return found;
}).filter((s): s is (typeof SHORTCUTS)[number] => s !== undefined);

// Teclas no formato "variante Mac / variante demais": exibe só a da plataforma atual.
function platformKeys(keys: string): string {
  const [mac = keys, other] = keys.split(" / ");
  return other !== undefined && mac.includes("⌘") ? (IS_MAC ? mac : other) : keys;
}

export function AppShell({ entry, children }: { entry: NotebookEntry | null; children: ReactNode }) {
  const leftOpen = useWorkspace((s) => s.leftOpen);
  const rightOpen = useWorkspace((s) => s.rightOpen);
  const focusMode = useWorkspace((s) => s.focusMode);
  const leftWidth = useLayout((s) => s.sidePanelWidth);
  const rightWidth = useLayout((s) => s.rightPanelWidth);
  const setLeftWidth = useLayout((s) => s.setSidePanelWidth);
  const setRightWidth = useLayout((s) => s.setRightPanelWidth);
  const baseWidth = useRef(0);
  const showLeft = !focusMode && leftOpen;
  const showRight = !focusMode && rightOpen;

  // Listener global (também com foco no editor/inputs): Cmd/Ctrl+. (modo foco),
  // Cmd/Ctrl+B (lateral esquerda) e Alt+Cmd/Ctrl+B (lateral direita).
  useEffect(() => {
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (!mod || e.shiftKey) return;
      // Com Alt, e.key de "B" pode vir como "∫" no macOS: nesse caso vale a tecla física.
      const isB = e.key.toLowerCase() === "b" || (e.altKey && e.code === "KeyB");
      const isDot = e.key === ".";
      if (e.altKey ? !isB : !isB && !isDot) return;
      e.preventDefault();
      if (e.repeat) return;
      const ws = useWorkspace.getState();
      if (isB) (e.altKey ? ws.toggleRight : ws.toggleLeft)();
      else ws.toggleFocusMode();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
  return (
    <div className={styles.shell}>
      <Banner entry={entry} />
      <TabBar entry={entry} />
      <div className={styles.body}>
        {showLeft ? (
          <>
            <SidePanel side="left" label="Left panel" width={leftWidth}>
              <Explorer side="left" />
            </SidePanel>
            <ResizeHandle
              orientation="vertical"
              label="Resize left panel"
              onDragStart={() => {
                baseWidth.current = useLayout.getState().sidePanelWidth;
              }}
              onDrag={(d) => setLeftWidth(Math.min(baseWidth.current + d, window.innerWidth / 2))}
              onReset={() => setLeftWidth(DEFAULT_SIDE_PANEL_WIDTH)}
            />
          </>
        ) : null}
        <main className={styles.content}>{children}</main>
        {showRight ? (
          <>
            <ResizeHandle
              orientation="vertical"
              label="Resize right panel"
              onDragStart={() => {
                baseWidth.current = useLayout.getState().rightPanelWidth;
              }}
              onDrag={(d) => setRightWidth(Math.min(baseWidth.current - d, window.innerWidth / 2))}
              onReset={() => setRightWidth(DEFAULT_RIGHT_PANEL_WIDTH)}
            />
            <SidePanel side="right" label="Right panel" width={rightWidth}>
              <Explorer side="right" />
            </SidePanel>
          </>
        ) : null}
      </div>
      <footer className={styles.shortcutBar} aria-label="Keyboard shortcuts" data-testid="shortcut-bar">
        {FOOTER_SHORTCUTS.map(([keys, what]) => (
          <span key={keys}>
            <kbd>{platformKeys(keys)}</kbd>
            {what}
          </span>
        ))}
      </footer>
      <ShortcutsDialog />
      <AboutDialog />
    </div>
  );
}
