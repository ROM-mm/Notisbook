/**
 * Settings (rota `/settings`; `/spark` é alias legado).
 * Seção "Runtimes": pré-requisitos/JDKs, instalação a partir do
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
            Runtimes
          </h2>
          <p className={styles.text}>
            Each runtime (a Spark version or an AWS Glue image) is isolated and has its own kernel. Pick the notebook's runtime in
            the selector in the top bar.
          </p>
        </header>
        <SparkSettings />
      </section>
    </div>
  );
}
