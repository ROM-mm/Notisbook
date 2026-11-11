/**
 * Settings (rota `/settings`; `/spark` é alias legado).
 * Seção "Spark environments": pré-requisitos/JDKs, instalação a partir do
 * catálogo com progresso ao vivo e versões instaladas.
 */
import { SparkSettings } from "../spark/SparkSettings";
import styles from "./SettingsPage.module.css";

export function SettingsPage() {
  return (
    <div className={styles.page} data-testid="settings-page">
      <section className={styles.section} aria-labelledby="settings-spark-title" data-testid="settings-spark">
        <header className={styles.header}>
          <h2 id="settings-spark-title" className={styles.title}>
            Spark environments
          </h2>
          <p className={styles.text}>
            Each Spark version becomes an isolated environment (uv + PySpark) with its own kernel. Pick the notebook's environment in
            the selector in the top bar.
          </p>
        </header>
        <SparkSettings />
      </section>
    </div>
  );
}
