/**
 * Install: combobox agrupado, sem campo de texto livre. LOCAL vem de `GET /api/spark/catalog`
 * (versões já instaladas ficam desabilitadas); DOCKER vem de `GET /api/docker/runtimes` e,
 * ao instalar, abre a janela própria do Docker em vez de disparar o job Local.
 */
import { useEffect, useState } from "react";
import { errorMessage } from "../../api/http";
import type { DockerRuntime, DockerRuntimes, Prereqs, SparkCatalog } from "../../api/types";
import type { Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" });
}

/** Linha do Spark sem JDK compatível segundo os prereqs (a instalação falharia com erro de JDK). */
function jdkMissing(version: string, prereqs: Prereqs | null): string | null {
  if (!prereqs) return null;
  const major = Number(version.split(".")[0]);
  if (major >= 4 && !prereqs.java.spark4_ok) return "No JDK 21/17 found: the Spark 4.x installation will fail.";
  if (major === 3 && !prereqs.java.spark3_ok) return "JDK 17 not found: the Spark 3.x installation will fail.";
  return null;
}

const DOCKER_PREFIX = "docker:";

interface Props {
  catalog: Loadable<SparkCatalog>;
  docker: Loadable<DockerRuntimes>;
  prereqs: Prereqs | null;
  /** Versões com instalação em andamento. */
  busyVersions: Set<string>;
  onInstall: (version: string) => Promise<void>;
  /** Abre a janela de instalação do runtime Docker escolhido. */
  onInstallDocker: (runtime: DockerRuntime) => void;
  onReloadCatalog: () => void;
}

export function InstallPanel({ catalog, docker, prereqs, busyVersions, onInstall, onInstallDocker, onReloadCatalog }: Props) {
  const versions = catalog.data?.versions ?? [];
  const runtimes = docker.data?.runtimes ?? [];
  const [selected, setSelected] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seleção padrão: a versão mais recente ainda não instalada.
  useEffect(() => {
    if (selected.startsWith(DOCKER_PREFIX)) return; // escolha Docker é do usuário; só a Local tem padrão
    const current = versions.find((v) => v.version === selected);
    if (current && !current.installed) return;
    const first = versions.find((v) => !v.installed && !busyVersions.has(v.version));
    setSelected(first?.version ?? "");
    // Só reage a um novo catálogo (a escolha do usuário é preservada).
  }, [catalog.data]);

  const chosenDocker = selected.startsWith(DOCKER_PREFIX) ? runtimes.find((r) => r.key === selected.slice(DOCKER_PREFIX.length)) : undefined;
  const chosen = chosenDocker ? undefined : versions.find((v) => v.version === selected);
  const dockerReady = !!chosenDocker && chosenDocker.available && !chosenDocker.installed && !chosenDocker.busy;
  const canInstall = chosenDocker
    ? dockerReady
    : !!chosen && !chosen.installed && !busyVersions.has(chosen.version) && !submitting;
  const warn = chosen ? jdkMissing(chosen.version, prereqs) : null;
  const fallback = catalog.data && (catalog.data.fallback || catalog.data.source === "fallback");

  const submit = async () => {
    if (chosenDocker) {
      setError(null);
      onInstallDocker(chosenDocker);
      return;
    }
    if (!chosen) return;
    setSubmitting(true);
    setError(null);
    try {
      await onInstall(chosen.version);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.block} data-testid="spark-install">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>Install</h3>
        <button type="button" className="btn btn-ghost" onClick={onReloadCatalog} disabled={catalog.loading}>
          {catalog.loading ? "Loading…" : "Refresh catalog"}
        </button>
      </div>
      <p className={styles.text}>
        {chosenDocker ? "Runs inside a Docker container; nothing is installed on this machine." : "Stable PySpark releases in the last 180 days (PyPI)."}
      </p>
      {fallback ? (
        <p className={styles.notice} data-testid="spark-catalog-fallback">
          {catalog.data?.source === "fallback"
            ? "PyPI unavailable — showing the list of known versions."
            : "No releases in the last 180 days — showing the latest stable versions."}
        </p>
      ) : null}
      {catalog.error ? <p className={styles.error}>Could not load the catalog: {catalog.error}</p> : null}
      {docker.error ? <p className={styles.error}>Could not load the Docker runtimes: {docker.error}</p> : null}
      <div className={styles.installRow}>
        <label className={styles.selectWrap}>
          <span className="visually-hidden">Runtime to install</span>
          <select
            className={`input ${styles.select}`}
            data-testid="spark-version-select"
            value={selected}
            disabled={versions.length === 0 && runtimes.length === 0}
            onChange={(e) => {
              setSelected(e.target.value);
              setError(null);
            }}
          >
            <optgroup label="LOCAL">
            {versions.map((v) => {
              const date = formatDate(v.released_at);
              const busy = busyVersions.has(v.version);
              const tag = v.installed ? " — installed" : busy ? " — installing" : "";
              return (
                <option key={v.version} value={v.version} disabled={v.installed || busy}>
                  {`Spark ${v.version}${date ? ` · ${date}` : ""}${tag}`}
                </option>
              );
            })}
            </optgroup>
            {runtimes.length > 0 ? (
              <optgroup label="DOCKER">
                {runtimes.map((r) => (
                  <option key={r.key} value={`${DOCKER_PREFIX}${r.key}`} disabled={r.installed || r.busy || !r.available}>
                    {`${r.label} · ${r.image}${r.installed ? " — installed" : r.busy ? " — installing" : !r.available ? " — Docker unavailable" : ""}`}
                  </option>
                ))}
              </optgroup>
            ) : null}
          </select>
        </label>
        <button type="button" className="btn btn-primary" data-testid="spark-install-button" disabled={!canInstall} onClick={() => void submit()}>
          {submitting ? "Submitting…" : chosenDocker ? "Install…" : "Install"}
        </button>
      </div>
      {versions.length > 0 && versions.every((v) => v.installed) && !chosenDocker ? <p className={styles.text}>All catalog versions are already installed.</p> : null}
      {warn ? <p className={styles.notice}>{warn}</p> : null}
      {error ? (
        <p className={styles.error} data-testid="spark-install-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
