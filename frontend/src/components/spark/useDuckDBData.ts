/**
 * Dados do runtime DuckDB (Settings → Runtimes): status, extensões do manifesto e job de instalação.
 *
 * - O job é acompanhado por um `JobStream`; um job em andamento (`installing`) é reconectado ao abrir.
 * - Sessões são relidas periodicamente: instalar/remover fica bloqueado com sessão do kernel
 *   aberta (o backend responde 409).
 * - Ao terminar instalação ou remoção, recarrega status/extensões e os kernelspecs das abas.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getDuckDBExtensions, getDuckDBStatus, installDuckDB, removeDuckDB } from "../../api/duckdb";
import { errorMessage } from "../../api/http";
import { listSessions } from "../../api/kernels";
import { getJob } from "../../api/spark";
import type { DuckDBExtensions, DuckDBStatus, SessionInfo } from "../../api/types";
import { JobStream } from "../../ws/jobs";
import { refreshKernelspecs } from "../../state/workspace";
import type { InstallJob, Loadable } from "./useSparkData";

const SESSIONS_POLL_MS = 4000;

function useLoadable<T>(fetcher: (signal?: AbortSignal) => Promise<T>) {
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

export function useDuckDBData() {
  const [status, reloadStatus] = useLoadable<DuckDBStatus>(getDuckDBStatus);
  const [extensions, reloadExtensions] = useLoadable<DuckDBExtensions>(getDuckDBExtensions);
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
    await Promise.all([reloadStatus(), reloadExtensions(), reloadSessions(), refreshKernelspecs().catch(() => undefined)]);
  }, [reloadStatus, reloadExtensions, reloadSessions]);

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
    void reloadExtensions();
    void reloadSessions();
    void reloadStatus().then((s) => {
      if (s?.installing) attach(s.installing.job_id, s.version);
    });
    const timer = window.setInterval(() => void reloadSessions(), SESSIONS_POLL_MS);
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
      stream.current?.close();
      stream.current = null;
    };
  }, [reloadStatus, reloadExtensions, reloadSessions, attach]);

  /** POST /api/duckdb/install e acompanha o job. Lança em erro (422/409). */
  const install = useCallback(async () => {
    const { job_id } = await installDuckDB();
    attach(job_id, status.data?.version ?? null);
    void reloadStatus();
  }, [attach, reloadStatus, status.data?.version]);

  /** DELETE /api/duckdb. Lança em erro (404/409/500); recarrega mesmo assim. */
  const remove = useCallback(async () => {
    try {
      await removeDuckDB();
    } finally {
      await refreshAfterChange();
    }
  }, [refreshAfterChange]);

  const dismissJob = useCallback(() => {
    stream.current?.close();
    stream.current = null;
    setJob(null);
  }, []);

  return { status, extensions, sessions, job, install, remove, dismissJob, reloadStatus, reloadExtensions };
}
