/**
 * Dados de Settings → Runtimes agregados: Spark local e Docker (via `useSparkData`) e DuckDB
 * (`GET /api/duckdb`), com um só fluxo de jobs de instalação, cada job marcado pelo `kind`.
 *
 * - Jobs DuckDB são acompanhados por `JobStream` (como os do Spark); instalações em andamento
 *   (`installing` com kind `duckdb-install`) são reconectadas ao abrir. Jobs de libs ficam com o
 *   diálogo Config de cada ambiente.
 * - Ao terminar instalação/remoção do DuckDB, recarrega o status e os kernelspecs das abas.
 * - As sessões vêm de `useSparkData` (uma só consulta periódica para todos os runtimes).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { duckdbKernelName, getDuckDBStatus, installDuckDBVersion, removeDuckDBVersion } from "../../api/duckdb";
import { errorMessage } from "../../api/http";
import { getJob } from "../../api/spark";
import type { DuckDBStatus } from "../../api/types";
import { JobStream } from "../../ws/jobs";
import { refreshKernelspecs } from "../../state/workspace";
import { type InstallJob, useLoadable, useSparkData } from "./useSparkData";

export type RuntimeJobKind = "spark" | "docker" | "duckdb";

export interface RuntimeJob extends InstallJob {
  kind: RuntimeJobKind;
}

export function useRuntimesData() {
  const spark = useSparkData();
  const [duckdb, reloadDuckDB] = useLoadable<DuckDBStatus>(getDuckDBStatus);
  const [duckJobs, setDuckJobs] = useState<InstallJob[]>([]);
  const streams = useRef(new Map<string, JobStream>());
  const mounted = useRef(true);

  const refreshDuckDB = useCallback(async () => {
    await Promise.all([reloadDuckDB(), refreshKernelspecs().catch(() => undefined)]);
  }, [reloadDuckDB]);

  const patchJob = useCallback((id: string, patch: (j: InstallJob) => Partial<InstallJob>) => {
    if (!mounted.current) return;
    setDuckJobs((list) => list.map((j) => (j.id === id ? { ...j, ...patch(j) } : j)));
  }, []);

  const attach = useCallback(
    (id: string, version: string | null) => {
      if (streams.current.has(id)) return;
      setDuckJobs((list) =>
        list.some((j) => j.id === id) ? list : [{ id, version, lines: [], phase: null, progress: 0, status: "running", message: null }, ...list],
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
          patchJob(id, (j) => ({ status: succeeded ? "succeeded" : "failed", message: line, progress: succeeded ? 1 : j.progress }));
          void refreshDuckDB();
        },
        onAbort: (_info, reason) => {
          streams.current.delete(id);
          // Sem `done` no stream: consulta o job para saber como terminou.
          getJob(id)
            .then((info) => {
              const finished = info.state === "succeeded" || info.state === "failed";
              patchJob(id, (j) => ({
                version: j.version ?? info.version,
                lines: info.log.length > j.lines.length ? info.log : j.lines,
                status: finished ? (info.state as "succeeded" | "failed") : "lost",
                message: info.error ?? (finished ? info.state : reason),
              }));
              if (finished) void refreshDuckDB();
            })
            .catch((err: unknown) => patchJob(id, () => ({ status: "lost", message: `${reason}: ${errorMessage(err)}` })));
        },
      });
      streams.current.set(id, stream);
    },
    [patchJob, refreshDuckDB],
  );

  // Carga inicial + reconexão às instalações DuckDB em andamento.
  useEffect(() => {
    mounted.current = true;
    void reloadDuckDB().then((s) => {
      for (const inst of (s?.installing ?? []).filter((i) => i.kind === "duckdb-install")) {
        const version = s?.catalog.find((c) => duckdbKernelName(c.version) === inst.kernel_name)?.version ?? null;
        attach(inst.job_id, version);
      }
    });
    const map = streams.current;
    return () => {
      mounted.current = false;
      for (const s of map.values()) s.close();
      map.clear();
    };
  }, [reloadDuckDB, attach]);

  /** POST /api/duckdb/versions e acompanha o job. Lança em erro (422/409). */
  const installDuckDB = useCallback(
    async (version: string) => {
      const { job_id } = await installDuckDBVersion(version);
      attach(job_id, version);
      void reloadDuckDB();
    },
    [attach, reloadDuckDB],
  );

  /** DELETE /api/duckdb/versions/{v}. Lança em erro (404/409/500); recarrega mesmo assim. */
  const removeDuckDB = useCallback(
    async (version: string) => {
      try {
        await removeDuckDBVersion(version);
      } finally {
        await refreshDuckDB();
      }
    },
    [refreshDuckDB],
  );

  const { jobs: sparkJobs, dismissJob: dismissSparkJob, docker } = spark;
  const dockerKeys = useMemo(() => new Set((docker.data?.runtimes ?? []).map((r) => r.key)), [docker.data]);

  /** Fluxo único: jobs DuckDB primeiro (mais recentes), depois Spark/Docker; `kind` separa a origem. */
  const jobs = useMemo<RuntimeJob[]>(
    () => [
      ...duckJobs.map((j) => ({ ...j, kind: "duckdb" as const })),
      ...sparkJobs.map((j) => ({ ...j, kind: j.version !== null && dockerKeys.has(j.version) ? ("docker" as const) : ("spark" as const) })),
    ],
    [duckJobs, sparkJobs, dockerKeys],
  );

  const dismissJob = useCallback(
    (id: string) => {
      if (!streams.current.has(id) && !duckJobs.some((j) => j.id === id)) {
        dismissSparkJob(id);
        return;
      }
      streams.current.get(id)?.close();
      streams.current.delete(id);
      setDuckJobs((list) => list.filter((j) => j.id !== id));
    },
    [duckJobs, dismissSparkJob],
  );

  const busyVersions = useMemo(
    () => new Set(jobs.filter((j) => j.kind === "spark" && j.status === "running" && j.version).map((j) => j.version as string)),
    [jobs],
  );
  const busyDuckDB = useMemo(
    () => new Set(jobs.filter((j) => j.kind === "duckdb" && j.status === "running" && j.version).map((j) => j.version as string)),
    [jobs],
  );

  return {
    ...spark,
    duckdb,
    jobs,
    busyVersions,
    busyDuckDB,
    installDuckDB,
    removeDuckDB,
    dismissJob,
    reloadDuckDB,
  };
}
