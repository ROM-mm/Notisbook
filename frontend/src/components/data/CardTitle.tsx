/** Título recolhível dos cartões das laterais (caixa alta, pequeno, espaçado): só o nome, que alterna o corpo ao clique. */
import styles from "./DataPanel.module.css";

interface CardTitleProps {
  id: string;
  label: string;
  collapsed: boolean;
  onToggle: () => void;
  title?: string;
}

export function CardTitle({ id, label, collapsed, onToggle, title }: CardTitleProps) {
  return (
    <h3 id={id} className={styles.sectionTitle} title={title}>
      <button type="button" className={styles.titleToggle} aria-expanded={!collapsed} onClick={onToggle}>
        <span className={styles.titleLabel}>{label}</span>
      </button>
    </h3>
  );
}
