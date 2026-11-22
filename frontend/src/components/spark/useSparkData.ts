/**
 * Dados da gestão do Spark (Settings → Ambientes Spark) e jobs de instalação.
 *
 * - Carrega prereqs, catálogo (PyPI), versões instaladas e sessões ativas.
 * - Sessões são relidas periodicamente: o botão "Remover" fica desabilitado
 *   enquanto houver sessão aberta do kernel (o backend responde 409 nesse caso).
 * - Cada instalação é acompanhada por um `JobStream` (`/api/jobs/{id}/events`);
 *   instalações já em andamento (`installing`) são reconectadas ao abrir a página.
 * - Ao terminar uma instalação ou remoção, recarrega listas e os kernelspecs
 *   das abas abertas (seletor de ambiente da barra de abas).
 * - Runtimes Docker: lidos com a pasta Connections atual (localStorage, `state/files`) para o
 *   backend apontar montagens defasadas; seus jobs seguem o mesmo mecanismo das instalações Local.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { installDockerRuntime, listDockerRuntimes, removeDockerRuntime, restartDockerRuntime, stopDockerRuntime } from "../../api/docker";
import { errorMessage } from "../../api/http";
import { listSessions } from "../../api/kernels";
import { getJob, getPrereqs, getSparkCatalog, getSparkVersions, installSparkVersion, removeSparkVersion } from "../../api/spark";
import type { DockerRuntimes, Prereqs, SessionInfo, SparkCatalog, SparkVersions } from "../../api/types";
import type { JobEvent } from "../../ws/protocol";
import { JobStream } from "../../ws/jobs";
import { useFiles } from "../../state/files";
import { refreshKernelspecs } from "../../state/workspace";

export type JobStatus = "running" | "succeeded" | "failed" | "lost";

export interface InstallJob {
  id: string;
  version: string | null;
  lines: JobEvent[];
  phase: string | null;
  /** 0..1 (fração das fases do instalador). */
  progress: number;
  status: JobStatus;
  /** Linha final ("succeeded" | "failed: ...") ou erro do job. */
  message: string | null;
}

export interface Loadable<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

const SESSIONS_POLL_MS = 4000;

export function useLoadable<T>(fetcher: (signal?: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<Loadable<T>>({ data: null, error: null, loading: true });
  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const data = await fetcher();
      setState({ data, error: null, loading: false });
      return data;
    } catch (err) {
      setState((s) => ({ ...s, error: errorMessage(err), loading: false }));
      return null;
    }
  }, [fetcher]);
  return [state, reload] as const;
}

export function useSparkData() {
  const [prereqs, reloadPrereqs] = useLoadable<Prereqs>(getPrereqs);
  const [catalog, reloadCatalog] = useLoadable<SparkCatalog>(getSparkCatalog);
  const [versions, reloadVersions] = useLoadable<SparkVersions>(getSparkVersions);
  const connectionsDir = useFiles((s) => s.root);
  const fetchDocker = useCallback((signal?: AbortSignal) => listDockerRuntimes(connectionsDir, signal), [connectionsDir]);
  const [docker, reloadDocker] = useLoadable<DockerRuntimes>(fetchDocker);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [jobs, setJobs] = useState<InstallJob[]>([]);
  const streams = useRef(new Map<string, JobStream>());
  const mounted = useRef(true);
  // Ref: a identidade de `reloadDocker` muda com a Connections e não pode recriar `attach` (fecharia os streams).
  const reloadDockerRef = useRef(reloadDocker);
  reloadDockerRef.current = reloadDocker;
  const attachedDockerJobs = useRef(new Set<string>());

  const reloadSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      if (mounted.current) setSessions(list);
    } catch {
      /* mantém a última lista */
    }
  }, []);

  /** Após instalar/remover: listas, catálogo (marca de instalada) e kernelspecs das abas. */
  const refreshAfterChange = useCallback(async () => {
    await Promise.all([
      reloadVersions(),
      reloadCatalog(),
      reloadSessions(),
      reloadDockerRef.current(),
      refreshKernelspecs().catch(() => undefined),
    ]);
  }, [reloadVersions, reloadCatalog, reloadSessions]);

  const patchJob = useCallback((id: string, patch: (j: InstallJob) => Partial<InstallJob>) => {
    if (!mounted.current) return;
    setJobs((list) => list.map((j) => (j.id === id ? { ...j, ...patch(j) } : j)));
  }, []);

  const attach = useCallback(
    (id: string, version: string | null) => {
      if (streams.current.has(id)) return;
      setJobs((list) =>
        list.some((j) => j.id === id)
          ? list
          : [{ id, version, lines: [], phase: null, progress: 0, status: "running", message: null }, ...list],
      );
      const stream = new JobStream(id, {
        onReset: () => patchJob(id, () => ({ lines: [], phase: null, progress: 0 })),
        onEvent: (ev) =>
          patchJob(id, (j) => ({
            lines: [...j.lines, ev],
            phase: ev.phase,
            progress: typeof ev.progress === "number" ? Math.max(j.progress, ev.progress) : j.progress,
          })),
        onDone: (succeeded, line) => {
          streams.current.delete(id);
          patchJob(id, (j) => ({
            status: succeeded ? "succeeded" : "failed",
            message: line,
            progress: succeeded ? 1 : j.progress,
          }));
          void refreshAfterChange();
        },
        onAbort: (_info, reason) => {
          streams.current.delete(id);
          // Sem `done` no stream: consulta o job para saber como terminou.
          getJob(id)
            .then((job) => {
              const state = job.state;
              const finished = state === "succeeded" || state === "failed";
              patchJob(id, (j) => ({
                version: j.version ?? job.version,
                lines: job.log.length > j.lines.length ? job.log : j.lines,
                status: state === "succeeded" || state === "failed" ? state : "lost",
                message: job.error ?? (finished ? job.state : reason),
              }));
              if (finished) void refreshAfterChange();
            })
            .catch((err: unknown) => patchJob(id, () => ({ status: "lost", message: `${reason}: ${errorMessage(err)}` })));
        },
      });
      streams.current.set(id, stream);
    },
    [patchJob, refreshAfterChange],
  );

  // Carga inicial + reconexão às instalações em andamento.
  useEffect(() => {
    mounted.current = true;
    void reloadPrereqs();
    void reloadCatalog();
    void reloadSessions();
    void reloadVersions().then((v) => {
      // Jobs de libs são acompanhados pelo diálogo de cada ambiente, não por esta lista.
      for (const inst of (v?.installing ?? []).filter((i) => i.kind === "install")) {
        getJob(inst.job_id)
          .then((job) => mounted.current && attach(inst.job_id, job.version))
          .catch(() => mounted.current && attach(inst.job_id, null));
      }
    });
    const timer = window.setInterval(() => void reloadSessions(), SESSIONS_POLL_MS);
    const map = streams.current;
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
      for (const s of map.values()) s.close();
      map.clear();
    };
  }, [reloadPrereqs, reloadCatalog, reloadSessions, reloadVersions, attach]);

  // Runtimes Docker: carrega ao abrir e quando a Connections muda; reconecta a job em andamento.
  useEffect(() => {
    void reloadDocker();
  }, [reloadDocker]);

  useEffect(() => {
    for (const rt of docker.data?.runtimes ?? []) {
      if (!rt.job || attachedDockerJobs.current.has(rt.job.id)) continue;
      attachedDockerJobs.current.add(rt.job.id);
      attach(rt.job.id, rt.key);
    }
  }, [docker.data, attach]);

  /** POST /api/spark/versions e acompanha o job. Lança em erro (422/409). */
  const install = useCallback(
    async (version: string) => {
      const { job_id } = await installSparkVersion(version);
      attach(job_id, version);
      void reloadVersions();
    },
    [attach, reloadVersions],
  );

  /** DELETE /api/spark/versions/{v}. Lança em erro (404/409/422). */
  const remove = useCallback(
    async (version: string) => {
      try {
        await removeSparkVersion(version);
      } finally {
        await refreshAfterChange();
      }
    },
    [refreshAfterChange],
  );

  /** POST /api/docker/runtimes/{key}/install e acompanha o job; devolve o id. Lança em erro (422/409/404). */
  const installDocker = useCallback(
    async (key: string, recreate: boolean) => {
      const { job_id } = await installDockerRuntime(key, connectionsDir, recreate);
      attachedDockerJobs.current.add(job_id);
      attach(job_id, key);
      void reloadDocker();
      return job_id;
    },
    [attach, connectionsDir, reloadDocker],
  );

  /** Stop/Restart/Remove do container; recarrega a lista (e os kernelspecs) mesmo em erro. */
  const dockerAction = useCallback(
    async (key: string, action: "stop" | "restart" | "remove") => {
      try {
        if (action === "stop") await stopDockerRuntime(key);
        else if (action === "restart") await restartDockerRuntime(key);
        else await removeDockerRuntime(key);
      } finally {
        await refreshAfterChange();
      }
    },
    [refreshAfterChange],
  );

  const dismissJob = useCallback((id: string) => {
    streams.current.get(id)?.close();
    streams.current.delete(id);
    setJobs((list) => list.filter((j) => j.id !== id));
  }, []);

  return {
    prereqs,
    catalog,
    versions,
    docker,
    connectionsDir,
    sessions,
    jobs,
    install,
    remove,
    installDocker,
    dockerAction,
    dismissJob,
    reloadPrereqs,
    reloadCatalog,
    reloadDocker,
  };
}
