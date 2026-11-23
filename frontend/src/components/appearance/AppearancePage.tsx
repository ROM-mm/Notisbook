/**
 * Settings › Appearance (rota `/settings/appearance`): escolha das fontes de Interface, Code cell e
 * Markdown, no mesmo padrão visual da tela Runtimes. Nada muda no app antes de Apply (F5, ⌘S/Ctrl+S
 * ou o botão); a prévia ao vivo só afeta o bloco Preview, que redeclara as variáveis de fonte no
 * próprio contêiner.
 */
import { type CSSProperties, type KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  BUNDLED_FONTS,
  DEFAULT_APPEARANCE,
  type Appearance,
  type FontSlot,
  fontFamilyValue,
  isValidFontName,
  MAX_FONT_NAME,
  normalizeFontName,
  useAppearance,
} from "../../state/appearance";
import { fetchSystemFonts } from "../../api/appearance";
import { openHome, previousEntryIsApp } from "../../state/router";
import { isMac } from "../shell/platform";
import styles from "./AppearancePage.module.css";

const FIELDS: readonly { slot: FontSlot; label: string; caption: string }[] = [
  { slot: "interface", label: "Interface", caption: "menus, panels, dialogs" },
  { slot: "code", label: "Code cell + outputs", caption: "also tables and monospaced text" },
  { slot: "markdown", label: "Markdown", caption: "cell text" },
];

const SAVE_KEY = isMac() ? "⌘S" : "Ctrl+S";

const HELP =
  "Press F4 or click a field to pick a font, or type a font name. Code cell also sets outputs, tables and other " +
  `monospaced text. F5 or ${SAVE_KEY} applies, Esc discards pending changes, F3 exits, F1 shows this help.`;

const FONTS_TITLE_ID = "appearance-fonts-title";
const PREVIEW_TITLE_ID = "appearance-preview-title";

type FontGroup = "Bundled" | "System";
type FontOption = { name: string; group: FontGroup };
type OptionGroup = { group: FontGroup; items: { option: FontOption; index: number }[] };

type Message = { kind: "info" | "ok" | "error"; text: string };

/** Agrupa opções consecutivas do mesmo grupo, preservando o índice global (ids e aria-activedescendant). */
function groupOptions(options: readonly FontOption[]): OptionGroup[] {
  const groups: OptionGroup[] = [];
  options.forEach((option, index) => {
    const last = groups[groups.length - 1];
    if (last && last.group === option.group) last.items.push({ option, index });
    else groups.push({ group: option.group, items: [{ option, index }] });
  });
  return groups;
}

function leave(): void {
  if (previousEntryIsApp()) window.history.back();
  else openHome();
}

export function AppearancePage() {
  const current = useAppearance((s) => s.current);
  const apply = useAppearance((s) => s.apply);

  const [pending, setPending] = useState<Appearance>({ ...current });
  const lastCurrent = useRef(current);
  const [openSlot, setOpenSlot] = useState<FontSlot | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [systemFonts, setSystemFonts] = useState<readonly string[]>([]);
  const [message, setMessage] = useState<Message>({ kind: "info", text: "Choose the fonts, then press F5 to apply." });

  const rootRef = useRef<HTMLDivElement>(null);
  const fieldRefs = useRef<(HTMLInputElement | null)[]>([]);
  const lastField = useRef(0);
  const restoreValue = useRef("");
  const keepActiveVisible = useRef(false);

  useEffect(() => {
    fieldRefs.current[0]?.focus();
  }, []);

  // Outra aba/janela aplicou fontes: slots sem edição pendente acompanham `current`; os editados ficam.
  useEffect(() => {
    const previous = lastCurrent.current;
    lastCurrent.current = current;
    if (previous === current) return;
    setPending((p) => {
      const next = { ...p };
      for (const { slot } of FIELDS) if (p[slot] === previous[slot]) next[slot] = current[slot];
      return FIELDS.some(({ slot }) => next[slot] !== p[slot]) ? next : p;
    });
  }, [current]);

  // Falha ou `unsupported` resultam em lista vazia: só as empacotadas e o nome livre.
  useEffect(() => {
    const controller = new AbortController();
    void fetchSystemFonts(false, controller.signal).then((names) => {
      if (!controller.signal.aborted) setSystemFonts(names);
    });
    return () => controller.abort();
  }, []);

  const allOptions: FontOption[] = [
    ...BUNDLED_FONTS.map((name) => ({ name, group: "Bundled" as const })),
    ...systemFonts.filter((name) => !BUNDLED_FONTS.includes(name)).map((name) => ({ name, group: "System" as const })),
  ];
  const needle = filter === null ? "" : normalizeFontName(filter).toLowerCase();
  const options = needle === "" ? allOptions : allOptions.filter((o) => o.name.toLowerCase().includes(needle));

  // Navegação por teclado mantém o item ativo visível; o hover do mouse não rola a lista.
  useEffect(() => {
    if (!keepActiveVisible.current || openSlot === null || active < 0) return;
    keepActiveVisible.current = false;
    document.getElementById(`appearance-list-${openSlot}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, openSlot]);

  const focusField = (index: number) => {
    lastField.current = index;
    fieldRefs.current[index]?.focus();
  };

  const closeList = () => {
    setOpenSlot(null);
    setFilter(null);
    setActive(-1);
  };

  const openList = (index: number) => {
    const slot = FIELDS[index]?.slot;
    if (!slot) return;
    focusField(index);
    restoreValue.current = pending[slot];
    setFilter(null);
    const selected = allOptions.findIndex((o) => o.name === normalizeFontName(pending[slot]));
    keepActiveVisible.current = true;
    setActive(selected);
    setOpenSlot(slot);
  };

  const setValue = (slot: FontSlot, value: string) => setPending((p) => ({ ...p, [slot]: value }));

  const choose = (slot: FontSlot, name: string) => {
    setValue(slot, name);
    closeList();
  };

  // Normalização e validação ficam no store; a tela só reflete o resultado.
  const doApply = () => {
    const result = apply(pending);
    if (!result.ok) {
      const index = FIELDS.findIndex((f) => f.slot === result.slot);
      closeList();
      setMessage({ kind: "error", text: `Invalid font name in ${FIELDS[index]?.label}; nothing was applied.` });
      focusField(index);
      return;
    }
    setPending(result.applied);
    closeList();
    setMessage({ kind: "ok", text: "Appearance applied." });
  };

  const doReset = () => {
    setPending({ ...DEFAULT_APPEARANCE });
    closeList();
    setMessage({ kind: "info", text: "Defaults loaded; press Apply to use them." });
  };

  const discardPending = () => {
    const dirty = FIELDS.some(({ slot }) => pending[slot] !== current[slot]);
    setPending({ ...current });
    closeList();
    if (dirty) setMessage({ kind: "info", text: "Pending changes discarded." });
  };

  const showHelp = () => setMessage({ kind: "info", text: HELP });

  const onFieldKeyDown = (e: KeyboardEvent<HTMLInputElement>, index: number) => {
    const slot = FIELDS[index]?.slot;
    if (!slot) return;
    const isOpen = openSlot === slot;
    if (e.key === "F4" || (e.altKey && e.key === "ArrowDown")) {
      e.preventDefault();
      if (isOpen) closeList();
      else openList(index);
      return;
    }
    if (isOpen) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const step = e.key === "ArrowDown" ? 1 : -1;
        keepActiveVisible.current = true;
        if (options.length > 0) setActive((a) => (a < 0 ? (step > 0 ? 0 : options.length - 1) : (a + step + options.length) % options.length));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (active >= 0 && options[active]) choose(slot, options[active].name);
        else closeList();
      } else if (e.key === "Escape") {
        e.preventDefault();
        setValue(slot, restoreValue.current);
        closeList();
      }
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      openList(index);
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      focusField((index + (e.key === "ArrowDown" ? 1 : FIELDS.length - 1)) % FIELDS.length);
    }
  };

  // F5 e ⌘S/Ctrl+S aplicam de qualquer ponto enquanto a tela está montada: o navegador nunca recarrega nem abre
  // "Salvar página" (as edições pendentes se perderiam). F1, F3, F4 e Esc só agem com o foco dentro da tela; quem já
  // tratou o evento (campo) o marca com preventDefault. Só F3 sai da tela: a tecla do DevTools no Windows/Linux não
  // é interceptada.
  useEffect(() => {
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const save = e.key.toLowerCase() === "s" && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey;
      if (save || e.key === "F5") {
        e.preventDefault();
        doApply();
        return;
      }
      if (!rootRef.current?.contains(e.target as Node)) return;
      if (e.key === "F1") showHelp();
      else if (e.key === "F3") leave();
      else if (e.key === "F4") openList(lastField.current);
      else if (e.key === "Escape") discardPending();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const previewSlot = (slot: FontSlot): string => {
    if (openSlot === slot && active >= 0 && options[active]) return options[active].name;
    const typed = normalizeFontName(pending[slot]);
    return isValidFontName(typed) ? typed : current[slot];
  };
  const face = {
    interface: fontFamilyValue("interface", previewSlot("interface")),
    code: fontFamilyValue("code", previewSlot("code")),
    markdown: fontFamilyValue("markdown", previewSlot("markdown")),
  };
  const previewVars = {
    "--font-sans": face.interface,
    "--font-head": face.interface,
    "--font-display": face.interface,
    "--font-script": face.interface,
    "--font-content": face.markdown,
    "--font-code": face.code,
    "--font-mono": face.code,
  } as CSSProperties;

  const messageClass = message.kind === "error" ? styles.messageError : message.kind === "ok" ? styles.messageOk : "";

  return (
    <div className={styles.page} ref={rootRef} tabIndex={-1} data-testid="appearance-page">
      <header className={styles.header}>
        <h2 className={styles.title}>Appearance</h2>
        <p className={styles.text}>
          Fonts for the interface, code cells and Markdown. Nothing changes in the app until you apply; the preview updates live.
        </p>
      </header>

      <section className={styles.block} aria-labelledby={FONTS_TITLE_ID}>
        <div className={styles.blockHead}>
          <h3 className={styles.blockTitle} id={FONTS_TITLE_ID}>
            Fonts
          </h3>
          <button type="button" className="btn btn-ghost" onClick={doReset}>
            Reset to defaults
          </button>
        </div>
        <div className={styles.fields}>
          {FIELDS.map(({ slot, label, caption }, index) => {
            const isOpen = openSlot === slot;
            const dirty = pending[slot] !== current[slot];
            const invalid = !isValidFontName(normalizeFontName(pending[slot]));
            const listId = `appearance-list-${slot}`;
            return (
              <div className={styles.field} key={slot}>
                <div className={styles.fieldLabel}>
                  <label htmlFor={`appearance-${slot}`}>{label}</label>
                  <small className={styles.caption}>{caption}</small>
                </div>
                <div className={styles.combo}>
                  <input
                    id={`appearance-${slot}`}
                    ref={(el) => {
                      fieldRefs.current[index] = el;
                    }}
                    className={`${styles.input} ${invalid ? styles.inputInvalid : ""}`}
                    role="combobox"
                    aria-expanded={isOpen}
                    aria-controls={listId}
                    aria-autocomplete="list"
                    aria-activedescendant={isOpen && active >= 0 ? `${listId}-${active}` : undefined}
                    aria-invalid={invalid}
                    value={pending[slot]}
                    maxLength={MAX_FONT_NAME}
                    autoComplete="off"
                    spellCheck={false}
                    data-testid={`appearance-field-${slot}`}
                    onFocus={() => {
                      lastField.current = index;
                    }}
                    onClick={() => {
                      if (!isOpen) openList(index);
                    }}
                    onBlur={() => {
                      if (openSlot === slot) closeList();
                    }}
                    onChange={(e) => {
                      if (openSlot !== slot) restoreValue.current = pending[slot];
                      setValue(slot, e.target.value);
                      setFilter(e.target.value);
                      setActive(-1);
                      setOpenSlot(slot);
                    }}
                    onKeyDown={(e) => onFieldKeyDown(e, index)}
                  />
                  <span className={styles.chevron} aria-hidden="true">
                    {isOpen ? "▲" : "▼"}
                  </span>
                  {isOpen ? (
                    <div className={styles.list} role="listbox" id={listId} aria-label={`${label} fonts`}>
                      {options.length === 0 ? (
                        <div className={styles.listEmpty}>No font matches; Enter keeps the typed name.</div>
                      ) : (
                        groupOptions(options).map(({ group, items }) => {
                          const labelId = `${listId}-group-${group}`;
                          return (
                            <div key={group} role="group" aria-labelledby={labelId}>
                              <div className={styles.groupLabel} role="presentation" id={labelId}>
                                {group}
                              </div>
                              {items.map(({ option, index: i }) => (
                                <div
                                  key={`${option.group}:${option.name}`}
                                  id={`${listId}-${i}`}
                                  role="option"
                                  title={option.name}
                                  aria-selected={i === active}
                                  className={`${styles.option} ${i === active ? styles.optionActive : ""}`}
                                  style={{ fontFamily: fontFamilyValue(slot, option.name) }}
                                  onMouseDown={(e) => e.preventDefault()}
                                  onMouseEnter={() => setActive(i)}
                                  onClick={() => choose(slot, option.name)}
                                >
                                  {option.name}
                                </div>
                              ))}
                            </div>
                          );
                        })
                      )}
                    </div>
                  ) : null}
                </div>
                <span className={styles.status} aria-live="polite">
                  {invalid ? (
                    <span className={`${styles.badge} ${styles.badgeBad}`}>invalid</span>
                  ) : dirty ? (
                    <span className={`${styles.badge} ${styles.badgePending}`}>pending</span>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section
        className={styles.block}
        aria-labelledby={PREVIEW_TITLE_ID}
        style={previewVars}
        data-testid="appearance-preview"
      >
        <div className={styles.blockHead}>
          <h3 className={styles.blockTitle} id={PREVIEW_TITLE_ID}>
            Preview
          </h3>
        </div>
        <div className={styles.previewRow}>
          <span className={styles.fieldLabel}>Interface</span>
          <p className={styles.previewInterface}>File Edit View Run Settings Help ─ New notebook</p>
        </div>
        <div className={styles.previewRow}>
          <span className={styles.fieldLabel}>Code cell</span>
          <pre className={styles.previewCode}>{"def greet(name):\n    return f\"Hello, {name}!\""}</pre>
        </div>
        <div className={styles.previewRow}>
          <span className={styles.fieldLabel}>Markdown</span>
          <div className={styles.previewMarkdown}>
            <strong>Markdown</strong> text with <code>inline code</code> and accents: ação, coração, você.
          </div>
        </div>
      </section>

      <p className={`${styles.message} ${messageClass}`} role="status" data-testid="appearance-message">
        {message.text}
      </p>

      <div className={styles.actions}>
        <span className={styles.keys}>{SAVE_KEY} apply · Esc discard · F4 open list · F1 help</span>
        <div className={styles.buttons}>
          <button type="button" className="btn" onClick={leave}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={doApply}>
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}
