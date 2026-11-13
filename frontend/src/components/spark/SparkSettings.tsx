/**
 * Settings → Ambientes Spark: pré-requisitos, instalar versão do catálogo (Local) ou runtime
 * Docker com progresso ao vivo, e ambientes instalados (Local e Docker) com remoção.
 */
import { useState } from "react";
import type { DockerRuntime } from "../../api/types";
import { DockerInstallDialog } from "./DockerInstallDialog";
import { InstalledList } from "./InstalledList";
import { InstallPanel } from "./InstallPanel";
import { JobProgress } from "./JobProgress";
import { PrereqsPanel } from "./PrereqsPanel";
import { useSparkData } from "./useSparkData";
import styles from "./Spark.module.css";

/** Janela Docker aberta; `jobId` é o job que ela exibe (some da lista de jobs enquanto isso). */
interface DockerDialogState {
  key: string;
  recreate: boolean;
  jobId: string | null;
}

export function SparkSettings() {
  const { prereqs, catalog, versions, docker, connectionsDir, sessions, jobs, install, remove, installDocker, dockerAction, dismissJob, reloadPrereqs, reloadCatalog, reloadDocker } =
    useSparkData();
  const [dialog, setDialog] = useState<DockerDialogState | null>(null);
  const busyVersions = new Set(jobs.filter((j) => j.status === "running" && j.version).map((j) => j.version as string));
  const dialogRuntime = dialog ? docker.data?.runtimes.find((r) => r.key === dialog.key) : undefined;
  const listedJobs = jobs.filter((j) => j.id !== dialog?.jobId);

  const openDialog = (runtime: DockerRuntime, recreate: boolean) => {
    void reloadDocker();
    setDialog({ key: runtime.key, recreate, jobId: null });
  };

  return (
    <div className={styles.spark}>
      <PrereqsPanel state={prereqs} onReload={() => void reloadPrereqs()} />
      <InstallPanel
        catalog={catalog}
        docker={docker}
        prereqs={prereqs.data}
        busyVersions={busyVersions}
        onInstall={install}
        onInstallDocker={(rt) => openDialog(rt, false)}
        onReloadCatalog={() => void reloadCatalog()}
      />
      {listedJobs.length > 0 ? (
        <div className={styles.jobs} data-testid="spark-jobs" aria-live="polite">
          {listedJobs.map((j) => (
            <JobProgress key={j.id} job={j} onDismiss={() => dismissJob(j.id)} />
          ))}
        </div>
      ) : null}
      <InstalledList
        versions={versions}
        docker={docker}
        connectionsDir={connectionsDir}
        sessions={sessions}
        onRemove={remove}
        onDockerAction={dockerAction}
        onDockerRecreate={(rt) => openDialog(rt, true)}
      />
      {dialog && dialogRuntime ? (
        <DockerInstallDialog
          runtime={dialogRuntime}
          recreate={dialog.recreate}
          connectionsDir={connectionsDir}
          job={jobs.find((j) => j.id === dialog.jobId)}
          onStart={async () => {
            const jobId = await installDocker(dialog.key, dialog.recreate);
            setDialog((d) => (d ? { ...d, jobId } : d));
          }}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}
