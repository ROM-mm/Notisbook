/**
 * Settings → Runtimes: pré-requisitos, instalar pelo combo único (Spark local, DuckDB ou
 * runtime Docker) com progresso ao vivo, e a lista Installed unificada com Config e remoção.
 * Com `?runtime=<k>` na rota, rola até a seção desse runtime e a destaca por alguns segundos.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import type { DockerRuntime } from "../../api/types";
import { useRouter, type RuntimeKind } from "../../state/router";
import { DockerInstallDialog } from "./DockerInstallDialog";
import { InstalledList } from "./InstalledList";
import { InstallPanel } from "./InstallPanel";
import { JobProgress } from "./JobProgress";
import { PrereqsPanel } from "./PrereqsPanel";
import { type RuntimeJob, useRuntimesData } from "./useRuntimesData";
import type { Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

/** Janela Docker aberta; `jobId` é o job que ela exibe (some da lista de jobs enquanto isso). */
interface DockerDialogState {
  key: string;
  recreate: boolean;
  jobId: string | null;
}

/** Seções roláveis: todos os runtimes são instalados pelo mesmo painel Install. */
type TargetSection = "install";

const SECTION_OF: Record<RuntimeKind, TargetSection> = { local: "install", docker: "install", duckdb: "install" };

/** Tempo com o destaque visível antes de começar a desvanecer. */
const HIGHLIGHT_MS = 2500;

/** Primeira carga resolvida (sucesso ou erro); recargas mantêm `data`/`error`, então não volta a `false`. */
const settled = (s: Loadable<unknown>) => !s.loading || s.data !== null || s.error !== null;

/**
 * Rola até a seção do runtime alvo da rota; devolve os refs das seções e a destacada (some após `HIGHLIGHT_MS`).
 * `ready`: os painéis acima das seções já carregaram — rolar antes deixaria o alvo fora de posição quando eles crescem.
 */
function useRuntimeTarget(ready: boolean): { refs: Record<TargetSection, RefObject<HTMLDivElement | null>>; highlighted: TargetSection | null } {
  const route = useRouter((s) => s.route);
  const installRef = useRef<HTMLDivElement>(null);
  const [highlighted, setHighlighted] = useState<TargetSection | null>(null);

  useEffect(() => {
    const runtime = route.view === "settings" ? route.runtime : undefined;
    if (!runtime) {
      setHighlighted(null);
      return;
    }
    if (!ready) return;
    const section = SECTION_OF[runtime];
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    installRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    setHighlighted(section);
    const timer = window.setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
    // Depende do objeto `route` (novo a cada navegação): reabrir o mesmo alvo destaca de novo.
    // `ready` só vai de false a true, então rola uma vez por navegação, assim que a carga assenta.
  }, [route, ready]);

  return { refs: { install: installRef }, highlighted };
}

/** Título do job por origem: Spark e DuckDB pela versão; Docker pelo rótulo do runtime. */
function jobTitle(job: RuntimeJob, runtimes: DockerRuntime[] | undefined): string {
  if (job.kind === "duckdb") return `DuckDB ${job.version ?? "…"}`;
  if (job.kind === "docker") return runtimes?.find((r) => r.key === job.version)?.label ?? `Docker ${job.version ?? "…"}`;
  return `Spark ${job.version ?? "…"}`;
}

export function SparkSettings() {
  const {
    prereqs,
    catalog,
    versions,
    duckdb,
    docker,
    connectionsDir,
    sessions,
    jobs,
    busyVersions,
    busyDuckDB,
    install,
    remove,
    installDuckDB,
    removeDuckDB,
    installDocker,
    dockerAction,
    dismissJob,
    reloadPrereqs,
    reloadCatalog,
    reloadDuckDB,
    reloadDocker,
  } = useRuntimesData();
  const [dialog, setDialog] = useState<DockerDialogState | null>(null);
  const dialogRuntime = dialog ? docker.data?.runtimes.find((r) => r.key === dialog.key) : undefined;
  const listedJobs = jobs.filter((j) => j.id !== dialog?.jobId);
  const { refs, highlighted } = useRuntimeTarget([prereqs, catalog, versions, duckdb, docker].every(settled));
  const targetClass = (section: TargetSection) => `${styles.target}${highlighted === section ? ` ${styles.targetActive}` : ""}`;

  const openDialog = (runtime: DockerRuntime, recreate: boolean) => {
    void reloadDocker();
    setDialog({ key: runtime.key, recreate, jobId: null });
  };

  return (
    <div className={styles.spark}>
      <PrereqsPanel state={prereqs} onReload={() => void reloadPrereqs()} />
      <div ref={refs.install} className={targetClass("install")} data-runtime-target="install">
        <InstallPanel
          catalog={catalog}
          duckdb={duckdb}
          docker={docker}
          prereqs={prereqs.data}
          busyVersions={busyVersions}
          busyDuckDB={busyDuckDB}
          onInstall={install}
          onInstallDuckDB={installDuckDB}
          onInstallDocker={(rt) => openDialog(rt, false)}
          onReloadCatalog={() => void Promise.all([reloadCatalog(), reloadDuckDB(), reloadDocker()])}
        />
      </div>
      {listedJobs.length > 0 ? (
        <div className={styles.jobs} data-testid="spark-jobs" aria-live="polite">
          {listedJobs.map((j) => (
            <JobProgress key={j.id} job={j} title={jobTitle(j, docker.data?.runtimes)} onDismiss={() => dismissJob(j.id)} />
          ))}
        </div>
      ) : null}
      <InstalledList
        versions={versions}
        duckdb={duckdb}
        docker={docker}
        connectionsDir={connectionsDir}
        sessions={sessions}
        onRemove={remove}
        onRemoveDuckDB={removeDuckDB}
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
