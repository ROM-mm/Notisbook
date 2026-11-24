/**
 * Settings → Runtimes: pré-requisitos, instalar versão do catálogo (Local) ou runtime
 * Docker com progresso ao vivo, e ambientes instalados (Local e Docker) com remoção.
 * Com `?runtime=<k>` na rota, rola até a seção desse runtime e a destaca por alguns segundos.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import type { DockerRuntime } from "../../api/types";
import { useRouter, type RuntimeKind } from "../../state/router";
import { DockerInstallDialog } from "./DockerInstallDialog";
import { DuckDBSettings } from "../duckdb/DuckDBSettings";
import { useDuckDBData } from "../duckdb/useDuckDBData";
import { InstalledList } from "./InstalledList";
import { InstallPanel } from "./InstallPanel";
import { JobProgress } from "./JobProgress";
import { PrereqsPanel } from "./PrereqsPanel";
import { useSparkData, type Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

/** Janela Docker aberta; `jobId` é o job que ela exibe (some da lista de jobs enquanto isso). */
interface DockerDialogState {
  key: string;
  recreate: boolean;
  jobId: string | null;
}

/** Seções roláveis: Spark local e Docker (Glue) são instalados pelo mesmo painel Install. */
type TargetSection = "install" | "duckdb";

const SECTION_OF: Record<RuntimeKind, TargetSection> = { local: "install", docker: "install", duckdb: "duckdb" };

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
  const duckdbRef = useRef<HTMLDivElement>(null);
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
    (section === "install" ? installRef : duckdbRef).current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    setHighlighted(section);
    const timer = window.setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
    // Depende do objeto `route` (novo a cada navegação): reabrir o mesmo alvo destaca de novo.
    // `ready` só vai de false a true, então rola uma vez por navegação, assim que a carga assenta.
  }, [route, ready]);

  return { refs: { install: installRef, duckdb: duckdbRef }, highlighted };
}

export function SparkSettings() {
  const { prereqs, catalog, versions, docker, connectionsDir, sessions, jobs, install, remove, installDocker, dockerAction, dismissJob, reloadPrereqs, reloadCatalog, reloadDocker } =
    useSparkData();
  const duck = useDuckDBData();
  const [dialog, setDialog] = useState<DockerDialogState | null>(null);
  const busyDuckDB = new Set(duck.job?.status === "running" && duck.job.version ? [duck.job.version] : []);
  const busyVersions = new Set(jobs.filter((j) => j.status === "running" && j.version).map((j) => j.version as string));
  const dialogRuntime = dialog ? docker.data?.runtimes.find((r) => r.key === dialog.key) : undefined;
  const listedJobs = jobs.filter((j) => j.id !== dialog?.jobId);
  const { refs, highlighted } = useRuntimeTarget([prereqs, catalog, versions, docker].every(settled));
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
          duckdb={duck.status}
          docker={docker}
          prereqs={prereqs.data}
          busyVersions={busyVersions}
          busyDuckDB={busyDuckDB}
          onInstall={install}
          onInstallDuckDB={duck.install}
          onInstallDocker={(rt) => openDialog(rt, false)}
          onReloadCatalog={() => void reloadCatalog()}
        />
      </div>
      {listedJobs.length > 0 || duck.job ? (
        <div className={styles.jobs} data-testid="spark-jobs" aria-live="polite">
          {duck.job ? <JobProgress job={duck.job} title={`DuckDB ${duck.job.version ?? ""}`.trim()} onDismiss={duck.dismissJob} /> : null}
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
      <div ref={refs.duckdb} className={targetClass("duckdb")} data-runtime-target="duckdb">
        <DuckDBSettings />
      </div>
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
