/**
 * Settings → Ambientes Spark: pré-requisitos, instalar versão do
 * catálogo com progresso ao vivo, e versões instaladas com remoção.
 */
import { InstalledList } from "./InstalledList";
import { InstallPanel } from "./InstallPanel";
import { JobProgress } from "./JobProgress";
import { PrereqsPanel } from "./PrereqsPanel";
import { useSparkData } from "./useSparkData";
import styles from "./Spark.module.css";

export function SparkSettings() {
  const { prereqs, catalog, versions, sessions, jobs, install, remove, dismissJob, reloadPrereqs, reloadCatalog } = useSparkData();
  const busyVersions = new Set(jobs.filter((j) => j.status === "running" && j.version).map((j) => j.version as string));

  return (
    <div className={styles.spark}>
      <PrereqsPanel state={prereqs} onReload={() => void reloadPrereqs()} />
      <InstallPanel
        catalog={catalog}
        prereqs={prereqs.data}
        busyVersions={busyVersions}
        onInstall={install}
        onReloadCatalog={() => void reloadCatalog()}
      />
      {jobs.length > 0 ? (
        <div className={styles.jobs} data-testid="spark-jobs" aria-live="polite">
          {jobs.map((j) => (
            <JobProgress key={j.id} job={j} onDismiss={() => dismissJob(j.id)} />
          ))}
        </div>
      ) : null}
      <InstalledList versions={versions} sessions={sessions} onRemove={remove} />
    </div>
  );
}
