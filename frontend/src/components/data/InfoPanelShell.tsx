/**
 * Moldura comum dos painéis laterais do Catalog (Table info e Catalog info): `aside` encaixado à
 * direita do conteúdo (não é modal), cabeçalho com ícone/título/caminho/fechar, selos e avisos,
 * abas com teclado (setas, Home/End), largura medida do conteúdo e estados de carga/erro.
 * Esc fecha apenas com o foco dentro do painel; `onClose` decide para onde o foco volta.
 */
import { useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { CloseIcon } from "../shell/icons";
import styles from "./InfoPanel.module.css";

export const DASH = "—";
const MIN_PANEL_WIDTH = 400;

export interface InfoTab<T extends string> {
  id: T;
  label: string;
}

/** Largura do painel que cabe o cabeçalho e o conteúdo da aba sem quebra; o teto (45vw) fica no CSS. */
function measurePanelWidth(
  panel: HTMLElement,
  head: HTMLElement,
  headText: HTMLElement,
  texts: HTMLElement[],
  body: HTMLElement | null,
  content: HTMLElement | null,
  callout: HTMLElement | null,
): number {
  const border = panel.offsetWidth - panel.clientWidth;
  const headNeed = head.clientWidth - headText.clientWidth + Math.max(0, ...texts.map((el) => el.scrollWidth));
  let bodyNeed = 0;
  if (body && content) {
    const cs = getComputedStyle(body);
    const padding = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const scrollbar = body.offsetWidth - body.clientWidth;
    // min-width:100% prenderia a medição à largura atual; zera só durante a leitura síncrona.
    const prev = content.style.minWidth;
    content.style.minWidth = "0";
    bodyNeed = content.offsetWidth + padding + scrollbar;
    content.style.minWidth = prev;
  }
  let calloutNeed = 0;
  const code = callout?.querySelector("code");
  if (callout && code) {
    const cs = getComputedStyle(callout);
    const sides = ["marginLeft", "marginRight", "paddingLeft", "paddingRight", "borderLeftWidth", "borderRightWidth"] as const;
    // `scrollWidth` é 0 em elemento inline; o retângulo dá a largura real do caminho (nowrap).
    calloutNeed = code.getBoundingClientRect().width + sides.reduce((sum, k) => sum + parseFloat(cs[k]), 0);
  }
  return Math.ceil(Math.max(MIN_PANEL_WIDTH, headNeed, bodyNeed, calloutNeed) + border);
}

/** Grade rótulo/valor; valor igual a `DASH` aparece atenuado. */
export function Facts({ facts }: { facts: [string, ReactNode][] }) {
  return (
    <dl className={styles.facts}>
      {facts.map(([label, value]) => (
        <div key={label} className={styles.fact}>
          <dt>{label}</dt>
          <dd className={value === DASH ? styles.na : undefined}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export interface InfoPanelShellProps<T extends string> {
  /** Id do `aside` (alvo do `aria-controls` das linhas da árvore); prefixa os ids das abas. */
  id: string;
  label: string;
  testId: string;
  /** Identidade do objeto aberto: mudou, a aba volta para a primeira. */
  resetKey: string;
  /** Muda quando os dados carregados mudam (dispara nova medição da largura). */
  measureKey: unknown;
  icon: ReactNode;
  title: string;
  titleHint: string;
  path: string;
  loading: boolean;
  error: string | null;
  /** Sem dados, o painel mostra só carga/erro; com dados, selos, avisos, callout e abas. */
  hasData: boolean;
  badges?: ReactNode;
  /** Avisos exibidos depois do erro (ex.: metadados indisponíveis). */
  notices?: ReactNode;
  /** Texto do callout; `undefined` omite o bloco (um `code` dentro dele entra na medição da largura). */
  callout?: ReactNode;
  tabs: readonly InfoTab<T>[];
  tablistLabel: string;
  renderTab: (tab: T) => ReactNode;
  onClose: () => void;
}

export function InfoPanelShell<T extends string>(props: InfoPanelShellProps<T>) {
  const { id, label, testId, resetKey, measureKey, icon, title, titleHint, path, loading, error, hasData } = props;
  const { badges, notices, callout, tabs, tablistLabel, renderTab, onClose } = props;
  const first = tabs[0]?.id as T;
  const [tab, setTab] = useState<T>(first);
  const tabRefs = useRef(new Map<T, HTMLButtonElement>());
  // Trocar de objeto volta para a primeira aba; releituras do mesmo objeto mantêm a aba.
  const [tabFor, setTabFor] = useState(resetKey);
  if (tabFor !== resetKey) {
    setTabFor(resetKey);
    setTab(first);
  }

  const panelRef = useRef<HTMLElement>(null);
  const headRef = useRef<HTMLElement>(null);
  const headTextRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const pathRef = useRef<HTMLSpanElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const calloutRef = useRef<HTMLParagraphElement>(null);
  const [width, setWidth] = useState(MIN_PANEL_WIDTH);

  // Remede ao trocar de objeto, dados ou aba, e de novo quando a fonte mono terminar de carregar.
  useLayoutEffect(() => {
    let cancelled = false;
    const measure = () => {
      const { current: panel } = panelRef;
      const { current: head } = headRef;
      const { current: headText } = headTextRef;
      if (cancelled || !panel || !head || !headText) return;
      const texts = [titleRef.current, pathRef.current].filter((el): el is HTMLElement => el !== null);
      setWidth(measurePanelWidth(panel, head, headText, texts, bodyRef.current, contentRef.current, calloutRef.current));
    };
    measure();
    void document.fonts.ready.then(measure);
    return () => {
      cancelled = true;
    };
  }, [resetKey, measureKey, tab]);

  function onKeyDown(e: KeyboardEvent<HTMLElement>) {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    e.preventDefault();
    onClose();
  }

  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    if (e.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    const nextId = tabs[next]?.id;
    if (!nextId) return;
    setTab(nextId);
    tabRefs.current.get(nextId)?.focus();
  }

  return (
    <aside
      ref={panelRef}
      id={id}
      aria-label={label}
      aria-busy={loading}
      className={styles.panel}
      style={{ width }}
      onKeyDown={onKeyDown}
      data-testid={testId}
    >
      <header ref={headRef} className={styles.head}>
        <span className={styles.headIcon}>{icon}</span>
        <div ref={headTextRef} className={styles.headText}>
          <h2 ref={titleRef} className={styles.title} title={titleHint}>
            {title}
          </h2>
          <span ref={pathRef} className={styles.path} title={path}>
            {path}
          </span>
        </div>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close" title="Close (Esc)">
          <CloseIcon size={14} />
        </button>
      </header>

      {hasData ? (
        <>
          {badges !== undefined ? <div className={styles.badges}>{badges}</div> : null}
          {error ? (
            <p className={`${styles.notice} ${styles.error}`} role="alert">
              {error}
            </p>
          ) : null}
          {notices}
          {callout !== undefined ? (
            <p ref={calloutRef} className={styles.callout}>
              {callout}
            </p>
          ) : null}
          <div className={styles.tabs} role="tablist" aria-label={tablistLabel}>
            {tabs.map((t, i) => (
              <button
                key={t.id}
                ref={(el) => {
                  if (el) tabRefs.current.set(t.id, el);
                  else tabRefs.current.delete(t.id);
                }}
                type="button"
                role="tab"
                id={`${id}-tab-${t.id}`}
                aria-selected={tab === t.id}
                aria-controls={`${id}-panel`}
                tabIndex={tab === t.id ? 0 : -1}
                className={`${styles.tab} ${tab === t.id ? styles.tabOn : ""}`}
                onClick={() => setTab(t.id)}
                onKeyDown={(e) => onTabKeyDown(e, i)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div
            ref={bodyRef}
            className={styles.body}
            role="tabpanel"
            id={`${id}-panel`}
            aria-labelledby={`${id}-tab-${tab}`}
            tabIndex={0}
          >
            <div ref={contentRef} className={styles.content}>
              {renderTab(tab)}
            </div>
          </div>
        </>
      ) : (
        <div className={styles.body}>
          {error ? (
            <p className={`${styles.empty} ${styles.error}`} role="alert">
              {error}
            </p>
          ) : loading ? (
            <p className={styles.empty}>Loading…</p>
          ) : null}
        </div>
      )}
    </aside>
  );
}
