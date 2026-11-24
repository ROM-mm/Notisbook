/**
 * Dados do runtime DuckDB (Settings → Runtimes): catálogo por versão, instaladas e job de instalação.
 *
 * - O job é acompanhado por um `JobStream`; um job em andamento (`installing`) é reconectado ao abrir.
 * - Sessões são relidas periodicamente: instalar/remover fica bloqueado com sessão do kernel
 *   aberta (o backend responde 409).
 * - Ao terminar instalação ou remoção, recarrega o status e os kernelspecs das abas.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getDuckDBStatus, installDuckDBVersion, removeDuckDBVersion } from "../../api/duckdb";
import { errorMessage } from "../../api/http";
import { listSessions } from "../../api/kernels";
import { getJob } from "../../api/spark";
import type { DuckDBStatus, SessionInfo } from "../../api/types";
import { JobStream } from "../../ws/jobs";
import { refreshKernelspecs } from "../../state/workspace";
import { useLoadable, type InstallJob } from "../spark/useSparkData";

const SESSIONS_POLL_MS = 4000;

export function useDuckDBData() {
  const [status, reloadStatus] = useLoadable<DuckDBStatus>(getDuckDBStatus);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [job, setJob] = useState<InstallJob | null>(null);
  const stream = useRef<JobStream | null>(null);
  const mounted = useRef(true);

  const reloadSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      if (mounted.current) setSessions(list);
    } catch {
      /* mantém a última lista */
    }
  }, []);

  const refreshAfterChange = useCallback(async () => {
    await Promise.all([reloadStatus(), reloadSessions(), refreshKernelspecs().catch(() => undefined)]);
  }, [reloadStatus, reloadSessions]);

  const patchJob = useCallback((patch: (j: InstallJob) => Partial<InstallJob>) => {
    if (mounted.current) setJob((j) => (j ? { ...j, ...patch(j) } : j));
  }, []);

  const attach = useCallback(
    (id: string, version: string | null) => {
      if (stream.current) return;
      setJob({ id, version, lines: [], phase: null, progress: 0, status: "running", message: null });
      stream.current = new JobStream(id, {
        onReset: () => patchJob(() => ({ lines: [], phase: null, progress: 0 })),
        onEvent: (ev) =>
          patchJob((j) => ({
            lines: [...j.lines, ev],
            phase: ev.phase,
            progress: typeof ev.progress === "number" ? Math.max(j.progress, ev.progress) : j.progress,
          })),
        onDone: (succeeded, line) => {
          stream.current = null;
          patchJob((j) => ({ status: succeeded ? "succeeded" : "failed", message: line, progress: succeeded ? 1 : j.progress }));
          void refreshAfterChange();
        },
        onAbort: (_info, reason) => {
          stream.current = null;
          // Sem `done` no stream: consulta o job para saber como terminou.
          getJob(id)
            .then((info) => {
              const finished = info.state === "succeeded" || info.state === "failed";
              patchJob((j) => ({
                lines: info.log.length > j.lines.length ? info.log : j.lines,
                status: finished ? (info.state as "succeeded" | "failed") : "lost",
                message: info.error ?? (finished ? info.state : reason),
              }));
              if (finished) void refreshAfterChange();
            })
            .catch((err: unknown) => patchJob(() => ({ status: "lost", message: `${reason}: ${errorMessage(err)}` })));
        },
      });
    },
    [patchJob, refreshAfterChange],
  );

  useEffect(() => {
    mounted.current = true;
    void reloadSessions();
    void reloadStatus().then((s) => {
      const inst = s?.installing.find((i) => i.kind === "duckdb-install");
      if (inst) attach(inst.job_id, null);
    });
    const timer = window.setInterval(() => void reloadSessions(), SESSIONS_POLL_MS);
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
      stream.current?.close();
      stream.current = null;
    };
  }, [reloadStatus, reloadSessions, attach]);

  /** POST /api/duckdb/versions e acompanha o job. Lança em erro (422/409). */
  const install = useCallback(
    async (version: string) => {
      const { job_id } = await installDuckDBVersion(version);
      attach(job_id, version);
      void reloadStatus();
    },
    [attach, reloadStatus],
  );

  /** DELETE /api/duckdb/versions/{v}. Lança em erro (404/409/500); recarrega mesmo assim. */
  const remove = useCallback(
    async (version: string) => {
      try {
        await removeDuckDBVersion(version);
      } finally {
        await refreshAfterChange();
      }
    },
    [refreshAfterChange],
  );

  const dismissJob = useCallback(() => {
    stream.current?.close();
    stream.current = null;
    setJob(null);
  }, []);

  return { status, sessions, job, install, remove, dismissJob, reloadStatus };
}
