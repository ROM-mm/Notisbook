/**
 * Layout raiz em coluna: banner da marca (56px), abas de notebooks e topbar
 * (cabeçalho + menu) em largura total, e abaixo delas uma linha com barra de ícones (Dados,
 * Notebooks), painel lateral recolhível e conteúdo.
 *
 * Pontos de extensão:
 * - `topbar`: a App monta a `Topbar` com a aba ativa (seletor de ambiente
 *   em `components/kernel/KernelSelector.tsx`).
 * - Painéis: `components/files/FileBrowser` (Notebooks) e
 *   `components/data/DataPanel` (Dados; por ora só visual).
 */
import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import { DEFAULT_SIDE_PANEL_WIDTH, useLayout } from "../../state/layout";
import { useWorkspace } from "../../state/workspace";
import { DataPanel } from "../data/DataPanel";
import { FileBrowser } from "../files/FileBrowser";
import { VariablesPanel } from "../variables/VariablesPanel";
import styles from "./AppShell.module.css";
import { Banner } from "./Banner";
import { ResizeHandle } from "./ResizeHandle";
import { AboutDialog } from "./AboutDialog";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { SidePanel } from "./SidePanel";
import { Sidebar } from "./Sidebar";
import { TabBar } from "./TabBar";

export function AppShell({ topbar, children }: { topbar: ReactNode; children: ReactNode }) {
  const panel = useWorkspace((s) => s.panel);
  const rightPanel = useWorkspace((s) => s.rightPanel);
  const railVisible = useWorkspace((s) => s.railVisible);
  const focusMode = useWorkspace((s) => s.focusMode);
  const sidePanelWidth = useLayout((s) => s.sidePanelWidth);
  const setSidePanelWidth = useLayout((s) => s.setSidePanelWidth);
  const baseWidth = useRef(sidePanelWidth);
  const sideOpen = !focusMode && (panel === "notebooks" || panel === "data");

  // Listener global (também com foco no editor/inputs): Cmd+. no Mac, Ctrl+. nos demais.
  useEffect(() => {
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (!mod || e.altKey || e.shiftKey || e.key !== ".") return;
      e.preventDefault();
      if (e.repeat) return;
      useWorkspace.getState().toggleFocusMode();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
  return (
    <div className={styles.shell}>
      <Banner />
      <TabBar />
      {topbar}
      <div className={styles.body} style={{ "--panel-width": `${sidePanelWidth}px` } as CSSProperties}>
        {railVisible && !focusMode ? <Sidebar /> : null}
        {sideOpen && panel === "notebooks" ? (
          <SidePanel title="Notebooks">
            <FileBrowser />
          </SidePanel>
        ) : null}
        {sideOpen && panel === "data" ? (
          <SidePanel title="Data">
            <DataPanel />
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
