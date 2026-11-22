/**
 * Settings › Appearance (rota `/settings/appearance`): escolha das fontes de Interface, Code cell e
 * Markdown em tela no estilo ISPF. Nada muda no app antes de Apply (F5, ⌘S ou APPLY); a prévia ao vivo
 * só afeta o bloco Preview, que redeclara as variáveis de fonte no próprio contêiner.
 */
import { type CSSProperties, Fragment, type KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  BUNDLED_FONTS,
  DEFAULT_APPEARANCE,
  type Appearance,
  type FontSlot,
  fontFamilyValue,
  isValidFontName,
  MAX_FONT_NAME,
  useAppearance,
} from "../../state/appearance";
import { fetchSystemFonts } from "../../api/appearance";
import { openHome, previousEntryIsApp } from "../../state/router";
import styles from "./AppearancePage.module.css";

const FIELDS: readonly { slot: FontSlot; label: string }[] = [
  { slot: "interface", label: "Interface" },
  { slot: "code", label: "Code cell + outputs" },
  { slot: "markdown", label: "Markdown" },
];

const HELP =
  "Type 1-3 or press F4 to pick a font. Code cell also sets outputs, tables and other monospaced text. F5 applies, F3/F12 exits, RESET restores the defaults.";

type FontGroup = "Bundled" | "System";
type FontOption = { name: string; group: FontGroup };

type Message = { kind: "info" | "ok" | "error"; text: string };

function leave(): void {
  if (previousEntryIsApp()) window.history.back();
  else openHome();
}

export function AppearancePage() {
  const current = useAppearance((s) => s.current);
  const apply = useAppearance((s) => s.apply);
  const reset = useAppearance((s) => s.reset);

  const [pending, setPending] = useState<Appearance>({ ...current });
  const [openSlot, setOpenSlot] = useState<FontSlot | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [systemFonts, setSystemFonts] = useState<readonly string[]>([]);
  const [command, setCommand] = useState("");
  const [message, setMessage] = useState<Message>({ kind: "info", text: "Choose the fonts, then press F5 to apply." });

  const rootRef = useRef<HTMLDivElement>(null);
  const commandRef = useRef<HTMLInputElement>(null);
  const fieldRefs = useRef<(HTMLInputElement | null)[]>([]);
  const lastField = useRef(0);
  const restoreValue = useRef("");
  const keepActiveVisible = useRef(false);

  useEffect(() => {
    commandRef.current?.focus();
  }, []);

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
  const needle = filter?.trim().toLowerCase() ?? "";
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
    const selected = allOptions.findIndex((o) => o.name === pending[slot].trim());
    keepActiveVisible.current = true;
    setActive(selected);
    setOpenSlot(slot);
  };

  const setValue = (slot: FontSlot, value: string) => setPending((p) => ({ ...p, [slot]: value }));

  const choose = (slot: FontSlot, name: string) => {
    setValue(slot, name);
    closeList();
  };

  const doApply = () => {
    const trimmed: Appearance = { ...DEFAULT_APPEARANCE };
    for (const { slot } of FIELDS) trimmed[slot] = pending[slot].trim();
    const result = apply(trimmed);
    if (!result.ok) {
      const index = FIELDS.findIndex((f) => f.slot === result.slot);
      closeList();
      setMessage({ kind: "error", text: `Invalid font name in ${FIELDS[index]?.label}; nothing was applied.` });
      focusField(index);
      return;
    }
    setPending(trimmed);
    closeList();
    setMessage({ kind: "ok", text: "Appearance applied." });
  };

  const doReset = () => {
    reset();
    setPending({ ...DEFAULT_APPEARANCE });
    closeList();
    setMessage({ kind: "ok", text: "Defaults restored." });
  };

  const discardPending = () => {
    const dirty = FIELDS.some(({ slot }) => pending[slot] !== current[slot]);
    setPending({ ...current });
    closeList();
    if (dirty) setMessage({ kind: "info", text: "Pending changes discarded." });
  };

  const runCommand = (raw: string) => {
    const cmd = raw.trim().toUpperCase();
    setCommand("");
    if (cmd === "") return;
    if (cmd === "APPLY") doApply();
    else if (cmd === "CANCEL") leave();
    else if (cmd === "RESET") doReset();
    else if (/^[1-3]$/.test(cmd)) focusField(Number(cmd) - 1);
    else setMessage({ kind: "error", text: `Invalid command: ${cmd}` });
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

  // Teclas de função e ⌘S valem em qualquer ponto da tela; quem já tratou o evento (campo) o marca com preventDefault.
  useEffect(() => {
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const save = e.key.toLowerCase() === "s" && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey;
      if (save) doApply();
      else if (e.key === "F1") showHelp();
      else if (e.key === "F3" || e.key === "F12") leave();
      else if (e.key === "F4") openList(lastField.current);
      else if (e.key === "F5") doApply();
      else if (e.key === "Escape" && rootRef.current?.contains(e.target as Node)) discardPending();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const previewSlot = (slot: FontSlot): string => {
    if (openSlot === slot && active >= 0 && options[active]) return options[active].name;
    const typed = pending[slot].trim();
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

  return (
    <div className={styles.page} ref={rootRef} data-testid="appearance-page">
      <header className={styles.titleLine}>
        <h2 className={styles.title}>APPEARANCE ─ Fonts</h2>
        <p
          className={`${styles.message} ${message.kind === "error" ? styles.messageError : message.kind === "ok" ? styles.messageOk : ""}`}
          role="status"
          data-testid="appearance-message"
        >
          {message.text}
        </p>
      </header>

      <div className={styles.commandLine}>
        <label htmlFor="appearance-command">Command ===&gt;</label>
        <input
          id="appearance-command"
          ref={commandRef}
          className={styles.commandInput}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              runCommand(command);
            }
          }}
          autoComplete="off"
          spellCheck={false}
          aria-describedby="appearance-command-hint"
          data-testid="appearance-command"
        />
      </div>
      <p id="appearance-command-hint" className={styles.hint}>
        APPLY  CANCEL  RESET  1-3 (go to field)
      </p>

      <div className={styles.fields}>
        {FIELDS.map(({ slot, label }, index) => {
          const isOpen = openSlot === slot;
          const dirty = pending[slot] !== current[slot];
          const invalid = !isValidFontName(pending[slot].trim());
          const listId = `appearance-list-${slot}`;
          return (
            <div className={styles.field} key={slot}>
              <label className={styles.fieldLabel} htmlFor={`appearance-${slot}`}>
                {index + 1}. {label}
              </label>
              <span className={styles.dots} aria-hidden="true">
                {".".repeat(80)}
              </span>
              <div className={styles.combo}>
                <input
                  id={`appearance-${slot}`}
                  ref={(el) => {
                    fieldRefs.current[index] = el;
                  }}
                  className={`${styles.input} ${dirty ? styles.inputPending : ""} ${invalid ? styles.inputInvalid : ""}`}
                  size={Math.min(MAX_FONT_NAME, Math.max(pending[slot].length, 1))}
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
                {isOpen ? (
                  <div className={styles.list} role="listbox" id={listId} aria-label={`${label} fonts`}>
                    {options.length === 0 ? (
                      <div className={styles.listEmpty}>No font matches; Enter keeps the typed name.</div>
                    ) : (
                      options.map((option, i) => (
                        <Fragment key={`${option.group}:${option.name}`}>
                          {i === 0 || options[i - 1]?.group !== option.group ? (
                            <div className={styles.groupLabel} role="presentation">
                              ── {option.group} ──
                            </div>
                          ) : null}
                          <div
                            id={`${listId}-${i}`}
                            role="option"
                            aria-selected={i === active}
                            className={`${styles.option} ${i === active ? styles.optionActive : ""}`}
                            style={{ fontFamily: fontFamilyValue(slot, option.name) }}
                            onMouseDown={(e) => e.preventDefault()}
                            onMouseEnter={() => setActive(i)}
                            onClick={() => choose(slot, option.name)}
                          >
                            {option.name}
                          </div>
                        </Fragment>
                      ))
                    )}
                  </div>
                ) : null}
              </div>
              <span className={`${styles.flag} ${invalid ? styles.flagInvalid : ""}`} aria-live="polite">
                {invalid ? "invalid" : dirty ? "*pending" : ""}
              </span>
            </div>
          );
        })}
      </div>

      <section className={styles.preview} aria-label="Preview" style={previewVars} data-testid="appearance-preview">
        <h3 className={styles.previewTitle}>Preview</h3>
        <p className={styles.previewInterface}>Interface: File Edit View Run Settings Help ─ New notebook</p>
        <pre className={styles.previewCode}>{"def greet(name):\n    return f\"Hello, {name}!\""}</pre>
        <div className={styles.previewMarkdown}>
          <strong>Markdown</strong> text with <code>inline code</code> and accents: ação, coração, você.
        </div>
      </section>

      <footer className={styles.footer}>
        <FooterKey label="F1=Help" onClick={showHelp} />
        <FooterKey label="F3=Exit" onClick={leave} />
        <FooterKey label="F4=List" onClick={() => openList(lastField.current)} />
        <FooterKey label="F5=Apply" onClick={doApply} />
        <FooterKey label="F12=Cancel" onClick={leave} />
      </footer>
    </div>
  );
}

function FooterKey({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className={styles.footerKey} onClick={onClick}>
      {label}
    </button>
  );
}
