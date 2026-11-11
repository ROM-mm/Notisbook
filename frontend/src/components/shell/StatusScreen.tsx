import type { ReactNode } from "react";
import { BrandMark } from "./icons";
import styles from "./StatusScreen.module.css";

/** Tela cheia para estados globais (carregando, não autorizado, erro). */
export function StatusScreen({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <BrandMark size={28} />
        <h1 className={styles.title}>{title}</h1>
        {children ? <div className={styles.body}>{children}</div> : null}
      </div>
    </div>
  );
}

/** Conteúdo provisório de uma view que outra sub-tarefa preencherá. */
export function Placeholder({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={styles.placeholder}>
      <h2 className={styles.placeholderTitle}>{title}</h2>
      {children ? <div className={styles.body}>{children}</div> : null}
    </div>
  );
}
