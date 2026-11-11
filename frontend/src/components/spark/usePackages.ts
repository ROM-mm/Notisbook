/**
 * Libs de um ambiente Spark: lista (`GET .../packages`) e jobs de adicionar/atualizar/desinstalar.
 *
 * - Um job por vez; o progresso vem do `JobStream`, com `getJob` como fallback se o stream cair.
 * - Ao abrir, se a lista traz `job_id` (job em andamento), reconecta a ele.
 * - Ao terminar, relê a lista e marca linhas alteradas (`changed`) e novas (`added`).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, errorMessage } from "../../api/http";
import { addPackages, getJob, listPackages, uninstallPackages, upgradePackages } from "../../api/spark";
import type { PackageItem, RequirementRow } from "../../api/types";
import { JobStream } from "../../ws/jobs";
import type { InstallJob } from "./useSparkData";

export type PackageAction = "add" | "upgrade" | "uninstall";

export interface PackagesResult {
  ok: boolean;
  text: string;
  /** Linhas do job para o "View log". */
  job: InstallJob;
}

/** Erro 422 por linha do Add: índice da linha e campo. */
export interface RowError {
  index: number;
  field: "name" | "spec";
  message: string;
}

const key = (name: string) => name.toLowerCase().replace(/[-_.]+/g, "-");

export function rowErrors(err: unknown): RowError[] | null {
  if (!(err instanceof ApiError) || err.status !== 422 || !Array.isArray(err.detail)) return null;
  const out: RowError[] = [];
  for (const d of err.detail as { loc?: unknown[]; msg?: unknown }[]) {
    const loc = d.loc ?? [];
    const index = loc[2];
    const field = loc[3];
    if (typeof index === "number" && (field === "name" || field === "spec")) {
      out.push({ index, field, message: String(d.msg) });
    }
  }
  return out.length > 0 ? out : null;
}

function summarize(action: PackageAction | null, before: PackageItem[], after: PackageItem[]): { text: string; changed: Set<string>; added: Set<string> } {
  const prev = new Map(before.map((p) => [key(p.name), p.version]));
  const changed = new Set<string>();
  const added = new Set<string>();
  const parts: string[] = [];
  for (const p of after) {
    const old = prev.get(key(p.name));
    if (old === undefined) {
      added.add(p.name);
      changed.add(p.name);
      parts.push(`${p.name} ${p.version}`);
    } else if (old !== p.version) {
      changed.add(p.name);
      parts.push(`${p.name} ${p.version}`);
    }
  }
  const gone = before.filter((p) => !after.some((a) => key(a.name) === key(p.name))).map((p) => p.name);
  if (action === "uninstall") {
    return { text: gone.length > 0 ? `Uninstalled ${gone.join(", ")}` : "No libraries were removed", changed, added };
  }
  if (action === null) {
    return { text: parts.length > 0 ? `Changed ${parts.join(", ")}` : "Libraries are up to date", changed, added };
  }
  const verb = action === "add" ? "Installed" : "Upgraded";
  return { text: parts.length > 0 ? `${verb} ${parts.join(", ")}` : "Everything was already up to date", changed, added };
}

export function usePackages(version: string) {
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<InstallJob | null>(null);
  const [result, setResult] = useState<PackagesResult | null>(null);
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const [added, setAdded] = useState<Set<string>>(new Set());
  const stream = useRef<JobStream | null>(null);
  const mounted = useRef(true);
  const before = useRef<PackageItem[]>([]);
  const action = useRef<PackageAction | null>("add");
  const [pending, setPending] = useState(false);

  const load = useCallback(async (): Promise<PackageItem[] | null> => {
    try {
      const data = await listPackages(version);
      if (!mounted.current) return null;
      setPackages(data.packages);
      setError(null);
      setLoading(false);
      return data.packages;
    } catch (err) {
      if (mounted.current) {
        setError(errorMessage(err));
        setLoading(false);
      }
      return null;
    }
  }, [version]);

  const finish = useCallback(
    async (finished: InstallJob) => {
      stream.current = null;
      const after = await load();
      if (!mounted.current) return;
      const ok = finished.status === "succeeded";
      if (ok && after) {
        const s = summarize(action.current, before.current, after);
        setChanged(s.changed);
        setAdded(s.added);
        setResult({ ok, text: s.text, job: finished });
      } else {
        setChanged(new Set());
        setAdded(new Set());
        const reason = (finished.message ?? "").replace(/^failed:\s*/, "");
        setResult({ ok: false, text: reason || "The operation failed", job: finished });
      }
      setJob(null);
    },
    [load],
  );

  const attach = useCallback(
    (id: string) => {
      if (!mounted.current) return;
      stream.current?.close();
      const state: InstallJob = { id, version, lines: [], phase: null, progress: 0, status: "running", message: null };
      let current = state;
      const update = (patch: Partial<InstallJob>) => {
        current = { ...current, ...patch };
        if (mounted.current) setJob(current);
      };
      setJob(current);
      stream.current = new JobStream(id, {
        onReset: () => update({ lines: [], phase: null }),
        onEvent: (ev) => update({ lines: [...current.lines, ev], phase: ev.phase }),
        onDone: (succeeded, line) => void finish({ ...current, status: succeeded ? "succeeded" : "failed", message: line, progress: 1 }),
        onAbort: (_info, reason) => {
          stream.current = null;
          getJob(id)
            .then((j) => {
              const done = j.state === "succeeded" || j.state === "failed";
              const next = { ...current, lines: j.log.length > current.lines.length ? j.log : current.lines, status: done ? j.state : "lost", message: j.error ?? (done ? j.state : reason) } as InstallJob;
              if (done) void finish(next);
              else update({ status: "lost", message: reason });
            })
            .catch((err: unknown) => update({ status: "lost", message: `${reason}: ${errorMessage(err)}` }));
        },
      });
    },
    [version, finish],
  );

  useEffect(() => {
    mounted.current = true;
    void listPackages(version)
      .then((data) => {
        if (!mounted.current) return;
        setPackages(data.packages);
        setLoading(false);
        if (data.job_id) {
          before.current = data.packages;
          action.current = data.job_action;
          attach(data.job_id);
        }
      })
      .catch((err: unknown) => {
        if (!mounted.current) return;
        setError(errorMessage(err));
        setLoading(false);
      });
    return () => {
      mounted.current = false;
      stream.current?.close();
      stream.current = null;
    };
  }, [version, attach]);

  const run = useCallback(
    async (kind: PackageAction, start: () => Promise<{ job_id: string }>) => {
      before.current = packages;
      action.current = kind;
      setResult(null);
      setChanged(new Set());
      setAdded(new Set());
      setPending(true);
      try {
        const { job_id } = await start();
        attach(job_id);
      } finally {
        if (mounted.current) setPending(false);
      }
    },
    [packages, attach],
  );

  return {
    packages,
    loading,
    error,
    job,
    pending,
    result,
    changed,
    added,
    reload: load,
    dismissResult: () => setResult(null),
    /** Lançam em erro (422 por linha — ver `rowErrors` —, 409, 404, 503). */
    add: (rows: RequirementRow[]) => run("add", () => addPackages(version, rows)),
    upgrade: (names: string[]) => run("upgrade", () => upgradePackages(version, names)),
    uninstall: (names: string[]) => run("uninstall", () => uninstallPackages(version, names)),
  };
}
