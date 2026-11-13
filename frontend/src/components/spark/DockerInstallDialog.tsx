/**
 * Janela de instalação/recriação de um runtime Docker: mostra o que vai rodar (Dockerfile,
 * imagem base, imagem gerada, container, pastas montadas), os passos do job e o log (`JobProgress`).
 * O job é criado pelo pai (`onStart`) e chega em `job`; fechar a janela não interrompe o job.
 * Modal nativo (`showModal`).
 */
import { useEffect, useRef, useState } from "react";
import type { DockerRuntime } from "../../api/types";
import dlg from "../../styles/dialog.module.css";
import { baseImage, dockerError, formatBytes } from "./DockerDetailsDialog";
import { JobProgress, type JobLabels } from "./JobProgress";
import type { InstallJob } from "./useSparkData";
import styles from "./Spark.module.css";

const STEPS = [
  { phase: "docker", label: "Docker available" },
  { phase: "image", label: "Image" },
  { phase: "container", label: "Container" },
  { phase: "validate", label: "Validating (Python, Spark, Glue, ipykernel)" },
  { phase: "kernelspec", label: "Registering the kernel for notebooks" },
] as const;

const RUNNING_LABEL: Record<string, string> = {
  docker: "Checking Docker",
  image: "Preparing the image",
  container: "Creating the container",
  validate: "Validating the environment",
  kernelspec: "Registering the kernel",
};

type StepState = "pending" | "running" | "done" | "failed";

function stepStates(job: InstallJob | undefined): StepState[] {
  if (!job) return STEPS.map(() => "pending");
  // Após reconexão o log vem do GET do job sem `phase` atualizado: usa a última linha.
  const phase = job.phase ?? job.lines.at(-1)?.phase;
  const current = STEPS.findIndex((s) => s.phase === phase);
  return STEPS.map((_, i) => {
    if (job.status === "succeeded") return "done";
    if (current < 0) return phase === "done" ? "done" : "pending";
    if (i < current) return "done";
    if (i > current) return "pending";
    return job.status === "running" ? "running" : "failed";
  });
}

const MARK: Record<StepState, string> = { pending: "○", running: "◐", done: "✓", failed: "✕" };

interface Props {
  runtime: DockerRuntime;
  /** Reinstala apagando o container (ex.: montagens defasadas). */
  recreate: boolean;
  connectionsDir: string | null;
  /** Job desta janela (null antes de iniciar). */
  job: InstallJob | undefined;
  /** Inicia o job; lança em erro 422/409/404. */
  onStart: () => Promise<void>;
  onClose: () => void;
}

export function DockerInstallDialog({ runtime, recreate, connectionsDir, job, onStart, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = job?.status === "running";
  const finished = job?.status === "succeeded";
  const verb = recreate ? "Recreate" : "Install";
  const states = stepStates(job);
  const size = formatBytes(runtime.image_size);
  const mounts = runtime.mounts?.current ?? null;

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  const start = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onStart();
    } catch (err) {
      setError(dockerError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const labels: JobLabels = {
    running: RUNNING_LABEL[job?.phase ?? ""] ?? "Starting…",
    succeeded: recreate ? "Runtime recreated" : "Runtime installed",
    failed: `${verb} failed`,
    log: `${verb} log`,
  };

  const stepText = (phase: (typeof STEPS)[number]["phase"], label: string) => {
    if (phase === "image")
      return runtime.image_present ? (
        <>
          Image <code className={styles.mono}>{runtime.image}</code> — already exists, build skipped
        </>
      ) : (
        <>
          Building image <code className={styles.mono}>{runtime.image}</code> from the Dockerfile (downloads the base image, a few GB)
        </>
      );
    if (phase === "container")
      return (
        <>
          {recreate ? "Recreating" : "Creating"} container <code className={styles.mono}>{runtime.container_name}</code>
        </>
      );
    return label;
  };

  return (
    <dialog
      ref={ref}
      className={`${dlg.dialog} ${styles.pkgDialog}`}
      aria-labelledby="docker-install-title"
      data-testid="docker-install-dialog"
      onCancel={(e) => running && e.preventDefault()}
      onClose={(e) => e.target === e.currentTarget && onClose()}
      onClick={(e) => e.target === e.currentTarget && !running && ref.current?.close()}
    >
      <div className={dlg.head}>
        <div>
          <h2 id="docker-install-title" className={dlg.title}>
            {verb} Docker environment · {runtime.label}
          </h2>
          <p className={styles.text}>This environment runs inside a container. Nothing is installed on this machine.</p>
        </div>
      </div>

      <dl className={`${styles.facts} ${styles.dockerFacts}`}>
        <dt>Dockerfile</dt>
        <dd className={styles.mono} data-testid="docker-install-dockerfile">
          {runtime.dockerfile.path}
        </dd>
        <dt>Base image</dt>
        <dd className={styles.mono}>{baseImage(runtime)}</dd>
        <dt>Built image</dt>
        <dd>
          <span className={styles.mono}>{runtime.image}</span>
          {runtime.image_present ? <span className={`${styles.tag} ${styles.tagNew}`}>already exists{size ? ` · ${size}` : ""}</span> : null}
        </dd>
        <dt>Container</dt>
        <dd className={styles.mono}>{runtime.container_name}</dd>
        <dt>Mounted folders</dt>
        <dd className={styles.mono} data-testid="docker-install-mounts">
          {mounts ? mounts.join(" · ") : connectionsDir ? `notebooks · warehouse · ${connectionsDir}` : "notebooks · warehouse"}
        </dd>
      </dl>

      {recreate ? <p className={styles.notice}>The current container will be removed and created again with the folders above. The image is kept.</p> : null}
      {!runtime.available ? <p className={styles.error}>Docker is not available. Start Docker (Colima or Docker Desktop) and try again.</p> : null}
      {runtime.mounts?.error ? <p className={styles.error}>{runtime.mounts.error}</p> : null}

      <ol className={styles.steps} data-testid="docker-install-steps">
        {STEPS.map((s, i) => (
          <li key={s.phase} className={`${styles.step} ${styles[`step_${states[i]}`] ?? ""}`} data-phase={s.phase} data-state={states[i]}>
            <span className={styles.stepMark} aria-hidden="true">
              {MARK[states[i] ?? "pending"]}
            </span>
            <span>{stepText(s.phase, s.label)}</span>
          </li>
        ))}
      </ol>

      {error ? (
        <p className={styles.error} data-testid="docker-install-error">
          {error}
        </p>
      ) : null}
      {job ? (
        <div className={styles.pkgJob}>
          <JobProgress job={job} title={runtime.label} labels={labels} />
        </div>
      ) : null}

      <div className={dlg.foot}>
        <button type="button" className="btn" disabled={running} onClick={() => ref.current?.close()}>
          {job ? "Close" : "Cancel"}
        </button>
        {finished ? null : (
          <button
            type="button"
            className="btn btn-primary"
            data-testid="docker-install-start"
            disabled={submitting || running || !runtime.available}
            onClick={() => void start()}
          >
            {submitting || running ? `${verb === "Install" ? "Installing" : "Recreating"}…` : job ? "Try again" : verb}
          </button>
        )}
      </div>
    </dialog>
  );
}
