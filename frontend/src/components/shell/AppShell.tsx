/**
 * Layout raiz em coluna: header (marca, menus e toggles, 56px) e abas de
 * notebooks (com os controles do kernel) em largura total, e abaixo delas uma
 * linha com o painel Explorer recolhível (⌘B) e o conteúdo.
 *
 * Pontos de extensão:
 * - `entry`: aba ativa (ou null), repassada ao header e à barra de abas
 *   (seletor de ambiente em `components/kernel/KernelSelector.tsx`).
 * - Explorer: `Explorer` empilha os cartões Catalog, Notebooks e Connections; um novo
 *   cartão entra em `state/layout.ts` (EXPLORER_CARDS) e em `Explorer.tsx`.
 */
import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import { DEFAULT_SIDE_PANEL_WIDTH, useLayout } from "../../state/layout";
import { type NotebookEntry, useWorkspace } from "../../state/workspace";
import { VariablesPanel } from "../variables/VariablesPanel";
import styles from "./AppShell.module.css";
import { Banner } from "./Banner";
import { Explorer } from "./Explorer";
import { ResizeHandle } from "./ResizeHandle";
import { AboutDialog } from "./AboutDialog";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { SidePanel } from "./SidePanel";
import { TabBar } from "./TabBar";

export function AppShell({ entry, children }: { entry: NotebookEntry | null; children: ReactNode }) {
  const rightPanel = useWorkspace((s) => s.rightPanel);
  const explorerOpen = useWorkspace((s) => s.explorerOpen);
  const focusMode = useWorkspace((s) => s.focusMode);
  const sidePanelWidth = useLayout((s) => s.sidePanelWidth);
  const setSidePanelWidth = useLayout((s) => s.setSidePanelWidth);
  const baseWidth = useRef(sidePanelWidth);
  const sideOpen = !focusMode && explorerOpen;

  // Listener global (também com foco no editor/inputs): Cmd/Ctrl+. (modo foco) e Cmd/Ctrl+B (Explorer).
  useEffect(() => {
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (!mod || e.altKey || e.shiftKey) return;
      const key = e.key.toLowerCase();
      if (key !== "." && key !== "b") return;
      e.preventDefault();
      if (e.repeat) return;
      const ws = useWorkspace.getState();
      if (key === ".") ws.toggleFocusMode();
      else ws.toggleExplorer();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
  return (
    <div className={styles.shell}>
      <Banner entry={entry} />
      <TabBar entry={entry} />
      <div className={styles.body} style={{ "--panel-width": `${sidePanelWidth}px` } as CSSProperties}>
        {sideOpen ? (
          <SidePanel title="Explorer">
            <Explorer />
          </SidePanel>
        ) : null}
        {sideOpen ? (
          <ResizeHandle
            orientation="vertical"
            label="Resize side panel"
            onDragStart={() => {
              baseWidth.current = useLayout.getState().sidePanelWidth;
            }}
            onDrag={(d) => setSidePanelWidth(Math.min(baseWidth.current + d, window.innerWidth / 2))}
            onReset={() => setSidePanelWidth(DEFAULT_SIDE_PANEL_WIDTH)}
          />
        ) : null}
        <main className={styles.content}>{children}</main>
        {!focusMode && rightPanel === "variables" ? <VariablesPanel /> : null}
      </div>
      <ShortcutsDialog />
      <AboutDialog />
    </div>
  );
}
