/**
 * Barra superior única do shell: marca N + "notisbook" (botão que alterna os menus),
 * menus File/Edit/View/Run/Help/About revelados no hover/foco da marca ou do próprio
 * menu, por clique/Enter/Espaço na marca ou com um menu aberto; Esc ou clique fora
 * fecham. Logo depois da marca, à esquerda: notebooks abertos lado a lado
 * (quadradinho verde no ativo = rota, cinza nos demais; não salvo em itálico; × no
 * hover, clique do meio fecha; "+" no fim) — a menubar revelada pela marca se
 * sobrepõe a essa lista enquanto visível. No canto direito: estado de salvamento,
 * controles do kernel do notebook ativo (seletor com estado, ▶, ■, ↻, ⋮) e os
 * toggles das laterais esquerda (⌘B) e direita (⌥⌘B) e do modo foco (⌘.).
 */
import { type FocusEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { useStore } from "zustand";
import { basename } from "../../lib/paths";
import { NotebookProvider, useNotebook } from "../../state/notebookContext";
import { activeNotebookPath, openNotebook, useRouter } from "../../state/router";
import { getEntry, type NotebookEntry, useWorkspace } from "../../state/workspace";
import { KernelToolbar } from "../kernel/KernelToolbar";
import styles from "./Banner.module.css";
import { CloseIcon, FocusIcon, HomeBrandMark, PanelLeftIcon, PanelRightIcon, PlusIcon } from "./icons";
import { MenuBar, newNotebook } from "./MenuBar";

function SaveState() {
  const saving = useNotebook((s) => s.saving);
  const saveError = useNotebook((s) => s.saveError);
  const dirty = useNotebook((s) => s.dirty);
  const ready = useNotebook((s) => s.status === "ready");
  if (!ready) return null;
  if (!saving && !saveError && dirty) return null;
  const text = saving ? "Saving…" : saveError ? "Save failed" : "Saved";
  return (
    <span className={saveError ? `${styles.saveText} ${styles.saveError}` : styles.saveText} title={saveError ?? undefined} data-testid="save-state">
      {text}
    </span>
  );
}

function PanelToggle({ side }: { side: "left" | "right" }) {
  const open = useWorkspace((s) => (side === "left" ? s.leftOpen : s.rightOpen) && !s.focusMode);
  const toggle = useWorkspace((s) => (side === "left" ? s.toggleLeft : s.toggleRight));
  const left = side === "left";
  return (
    <button
      type="button"
      className={styles.toggle}
      data-testid={`toggle-${side}-panel`}
      title={left ? "Left panel (⌘B)" : "Right panel (⌥⌘B)"}
      aria-label={left ? "Left panel" : "Right panel"}
      aria-pressed={open}
      onClick={toggle}
    >
      {left ? <PanelLeftIcon size={15} /> : <PanelRightIcon size={15} />}
    </button>
  );
}

function FocusToggle() {
  const on = useWorkspace((s) => s.focusMode);
  const toggle = useWorkspace((s) => s.toggleFocusMode);
  return (
    <button
      type="button"
      className={styles.toggle}
      data-testid="toggle-focus"
      title="Focus mode (⌘.)"
      aria-label="Focus mode"
      aria-pressed={on}
      onClick={toggle}
    >
      <FocusIcon size={15} />
    </button>
  );
}

function OpenNotebook({ path, active }: { path: string; active: boolean }) {
  const entry = getEntry(path);
  if (!entry) return null;
  return <OpenNotebookInner path={path} active={active} entry={entry} />;
}

function OpenNotebookInner({ path, active, entry }: { path: string; active: boolean; entry: NotebookEntry }) {
  const dirty = useStore(entry.notebook, (s) => s.dirty);
  const closeTab = useWorkspace((s) => s.closeTab);
  const name = basename(path);
  return (
    <div
      className={styles.nb}
      data-active={active || undefined}
      data-dirty={dirty || undefined}
      data-testid="notebook-tab"
      data-path={path}
      title={dirty ? `${path} · Unsaved changes` : path}
    >
      <button
        type="button"
        role="tab"
        aria-selected={active}
        className={styles.nbMain}
        onClick={() => openNotebook(path)}
        onAuxClick={(e) => e.button === 1 && closeTab(path)}
      >
        <span className={styles.nbMark} aria-hidden="true" />
        <span className={styles.nbLabel}>{name}</span>
        {dirty ? <span className={styles.srOnly}> (unsaved changes)</span> : null}
      </button>
      <button
        type="button"
        className={styles.nbClose}
        aria-label={`Close ${name}`}
        title="Close"
        data-testid="notebook-tab-close"
        onClick={() => closeTab(path)}
      >
        <CloseIcon size={10} />
      </button>
    </div>
  );
}

/** Notebooks abertos à esquerda da barra, logo após a marca; o "+" cria um notebook. */
function OpenNotebooks({ entry }: { entry: NotebookEntry | null }) {
  const tabs = useWorkspace((s) => s.tabs);
  const active = useRouter((s) => activeNotebookPath(s.route));
  if (tabs.length === 0) return null;
  return (
    <div className={styles.nbBar}>
      <div className={styles.nbList} role="tablist" aria-label="Open notebooks">
        {tabs.map((p) => (
          <OpenNotebook key={p} path={p} active={p === active} />
        ))}
      </div>
      <button
        type="button"
        className={styles.nbAdd}
        aria-label="New notebook"
        title="New notebook"
        data-testid="tab-new"
        onClick={() => newNotebook(entry)}
      >
        <PlusIcon size={13} />
      </button>
    </div>
  );
}

/**
 * Estado da área da marca: "auto" = menus aparecem só por hover/foco de teclado (CSS);
 * "open" = fixados por clique/teclado na marca; "closed" = dispensados (clique na
 * marca, Esc ou clique fora) mesmo com ponteiro/foco ainda na área — volta a "auto"
 * quando o ponteiro ou o foco entram de novo.
 */
type BrandMenuState = "auto" | "open" | "closed";

function BrandMenu({ entry }: { entry: NotebookEntry | null }) {
  const [state, setState] = useState<BrandMenuState>("auto");
  const areaRef = useRef<HTMLDivElement>(null);
  const brandRef = useRef<HTMLButtonElement>(null);
  const menubarId = useId();

  useEffect(() => {
    if (state !== "open") return;
    const onDown = (e: MouseEvent) => {
      if (areaRef.current && !areaRef.current.contains(e.target as Node)) setState("closed");
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [state]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    // Um dropdown aberto consome o próprio Esc (stopPropagation) e só se fecha; o Esc
    // com o dropdown fechado (foco na marca ou num gatilho File/Edit/…) chega aqui.
    if (e.key !== "Escape") return;
    e.preventDefault();
    setState("closed");
    if (e.target !== brandRef.current) brandRef.current?.focus();
  };

  const onFocus = (e: FocusEvent<HTMLDivElement>) => {
    const fromOutside = !areaRef.current?.contains(e.relatedTarget as Node | null);
    if (state === "closed" && (fromOutside || (e.target as Node) !== brandRef.current)) setState("auto");
  };

  return (
    <div
      ref={areaRef}
      className={styles.brandArea}
      data-state={state}
      onKeyDown={onKeyDown}
      onFocus={onFocus}
      onMouseEnter={() => setState((s) => (s === "closed" ? "auto" : s))}
    >
      <button
        ref={brandRef}
        type="button"
        className={styles.brand}
        aria-label="Notisbook menus"
        aria-expanded={state === "open"}
        aria-controls={menubarId}
        data-testid="brand-menu-toggle"
        onClick={() => setState((s) => (s === "open" ? "closed" : "open"))}
      >
        <HomeBrandMark size={18} />
        <span className={styles.wordmark}>notisbook</span>
      </button>
      <MenuBar entry={entry} id={menubarId} />
    </div>
  );
}

export function Banner({ entry }: { entry: NotebookEntry | null }) {
  return (
    <header className={styles.banner} aria-label="Notisbook">
      <BrandMenu entry={entry} />
      <OpenNotebooks entry={entry} />
      <div className={styles.actions}>
        {entry ? (
          <NotebookProvider entry={entry}>
            <SaveState />
            <KernelToolbar />
          </NotebookProvider>
        ) : null}
        <span className={styles.toggles}>
          <PanelToggle side="left" />
          <PanelToggle side="right" />
          <FocusToggle />
        </span>
      </div>
    </header>
  );
}
