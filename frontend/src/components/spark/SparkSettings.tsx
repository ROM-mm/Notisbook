/**
 * Settings → Runtimes: pré-requisitos, instalar pelo combo único (Spark local, DuckDB ou
 * runtime Docker) com progresso ao vivo, e a lista Installed unificada com Config e remoção.
 * Com `?runtime=<k>` na rota (local|docker|duckdb), rola até Install e pré-seleciona no combo o
 * item recomendado da categoria do runtime; se a categoria já está toda instalada, rola até
 * Installed. A seção alvo fica destacada por alguns segundos.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import type { DockerRuntime, DockerRuntimes, DuckDBStatus, SparkCatalog } from "../../api/types";
import { useRouter, type RuntimeKind } from "../../state/router";
import { DockerInstallDialog } from "./DockerInstallDialog";
import { InstalledList } from "./InstalledList";
import { type InstallTarget, InstallPanel } from "./InstallPanel";
import { JobProgress } from "./JobProgress";
import { PrereqsPanel } from "./PrereqsPanel";
import type { RuntimeCategory } from "./RuntimeCombo";
import { type RuntimeJob, useRuntimesData } from "./useRuntimesData";
import type { Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

/** Janela Docker aberta; `jobId` é o job que ela exibe (some da lista de jobs enquanto isso). */
interface DockerDialogState {
  key: string;
  recreate: boolean;
  jobId: string | null;
}

/** Seções roláveis do deep-link. */
type TargetSection = "install" | "installed";

/** Categoria do combo para cada runtime do deep-link. */
const CATEGORY_OF: Record<RuntimeKind, RuntimeCategory> = { local: "processing", duckdb: "analytics", docker: "docker" };

/** A categoria tem itens e todos já estão instalados (nada a instalar: o alvo vira a lista Installed). */
function categoryAllInstalled(category: RuntimeCategory, catalog: SparkCatalog | null, duckdb: DuckDBStatus | null, docker: DockerRuntimes | null): boolean {
  const flags =
    category === "processing"
      ? (catalog?.versions ?? []).map((v) => v.installed)
      : category === "analytics"
        ? (duckdb?.catalog ?? []).map((v) => v.installed)
        : (docker?.runtimes ?? []).map((r) => r.installed);
  return flags.length > 0 && flags.every(Boolean);
}

/** Tempo com o destaque visível antes de começar a desvanecer. */
const HIGHLIGHT_MS = 2500;

/** Primeira carga resolvida (sucesso ou erro); recargas mantêm `data`/`error`, então não volta a `false`. */
const settled = (s: Loadable<unknown>) => !s.loading || s.data !== null || s.error !== null;

/**
 * Deep-link `?runtime=<k>`: rola até Install (ou Installed, se a categoria está toda instalada),
 * destaca a seção (some após `HIGHLIGHT_MS`) e devolve o pedido de pré-seleção para o combo.
 * `ready`: os painéis já carregaram — rolar antes deixaria o alvo fora de posição quando eles crescem.
 * `allInstalled` é lida no momento do disparo (ref), sem refazer o efeito a cada render.
 */
function useRuntimeTarget(
  ready: boolean,
  allInstalled: (category: RuntimeCategory) => boolean,
): { refs: Record<TargetSection, RefObject<HTMLDivElement | null>>; highlighted: TargetSection | null; target: InstallTarget | null } {
  const route = useRouter((s) => s.route);
  const installRef = useRef<HTMLDivElement>(null);
  const installedRef = useRef<HTMLDivElement>(null);
  const allInstalledRef = useRef(allInstalled);
  allInstalledRef.current = allInstalled;
  const [highlighted, setHighlighted] = useState<TargetSection | null>(null);
  const [target, setTarget] = useState<InstallTarget | null>(null);

  useEffect(() => {
    const runtime = route.view === "settings" ? route.runtime : undefined;
    if (!runtime) {
      setHighlighted(null);
      return;
    }
    if (!ready) return;
    const category = CATEGORY_OF[runtime];
    const section: TargetSection = allInstalledRef.current(category) ? "installed" : "install";
    if (section === "install") setTarget((t) => ({ category, nonce: (t?.nonce ?? 0) + 1 }));
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    (section === "install" ? installRef : installedRef).current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    setHighlighted(section);
    const timer = window.setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
    // Depende do objeto `route` (novo a cada navegação): reabrir o mesmo alvo destaca de novo.
    // `ready` só vai de false a true, então rola uma vez por navegação, assim que a carga assenta.
  }, [route, ready]);

  return { refs: { install: installRef, installed: installedRef }, highlighted, target };
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
  const { refs, highlighted, target } = useRuntimeTarget([prereqs, catalog, versions, duckdb, docker].every(settled), (category) =>
    categoryAllInstalled(category, catalog.data, duckdb.data, docker.data),
  );
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
          target={target}
        />
      </div>
      {listedJobs.length > 0 ? (
        <div className={styles.jobs} data-testid="spark-jobs" aria-live="polite">
          {listedJobs.map((j) => (
            <JobProgress key={j.id} job={j} title={jobTitle(j, docker.data?.runtimes)} onDismiss={() => dismissJob(j.id)} />
          ))}
        </div>
      ) : null}
      <div ref={refs.installed} className={targetClass("installed")} data-runtime-target="installed">
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
