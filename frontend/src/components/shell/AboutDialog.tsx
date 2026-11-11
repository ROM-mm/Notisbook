/** Diálogo "About" (botão da topbar): marca, nome e autoria. */
import { useEffect, useRef } from "react";
import { useWorkspace } from "../../state/workspace";
import dlg from "../../styles/dialog.module.css";
import styles from "./AppShell.module.css";
import { BrandMark } from "./icons";

export function AboutDialog() {
  const open = useWorkspace((s) => s.aboutOpen);
  const setOpen = useWorkspace((s) => s.setAboutOpen);
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      // O link do GitHub é o primeiro focável; o foco inicial deve ficar em "Close".
      closeRef.current?.focus();
    }
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.aboutDialog}`}
      aria-labelledby="about-title"
      data-testid="about-dialog"
      onClose={() => setOpen(false)}
      onClick={(e) => e.target === e.currentTarget && setOpen(false)}
    >
      <div className={styles.aboutBody}>
        <BrandMark size={72} />
        <h2 id="about-title" className={styles.aboutName}>
          Notisbook
        </h2>
        <p className={styles.aboutAuthor}>by Romerito Morais</p>
        <a
          className={styles.aboutLink}
          href="https://github.com/ROM-mm"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="about-github"
        >
          github.com/ROM-mm
        </a>
        <button ref={closeRef} type="button" className="btn" data-testid="about-close" onClick={() => setOpen(false)}>
          Close
        </button>
      </div>
    </dialog>
  );
}
