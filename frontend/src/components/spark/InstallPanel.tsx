/**
 * Install: combo único (`RuntimeCombo`) com as categorias Data processing (Spark local, de
 * `GET /api/spark/catalog`), Analytics (DuckDB, de `GET /api/duckdb`) e Docker (Glue, de
 * `GET /api/docker/runtimes`). Escolher no combo só marca a opção; o botão Install dispara:
 * Spark → `POST /api/spark/versions`, DuckDB → `POST /api/duckdb/versions`, Docker → abre a
 * janela própria do Docker (DockerInstallDialog).
 */
import { useEffect, useMemo, useState } from "react";
import { duckdbKernelName } from "../../api/duckdb";
import { ApiError, errorMessage } from "../../api/http";
import type { DockerRuntime, DockerRuntimes, DuckDBStatus, Prereqs, SparkCatalog } from "../../api/types";
import { RuntimeCombo, type RuntimeCategory, type RuntimeOption } from "./RuntimeCombo";
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

/** 409 traz o motivo do backend (sessão aberta, job em andamento); mostra-o por inteiro. */
function installError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409) return `Blocked: ${err.message}`;
  return errorMessage(err);
}

const SPARK = "spark:";
const DUCKDB = "duckdb:";
const DOCKER = "docker:";

/** Pedido de pré-seleção vindo de fora (deep-link `?runtime=`): `nonce` novo repete o pedido. */
export interface InstallTarget {
  category: RuntimeCategory;
  nonce: number;
}

interface Props {
  catalog: Loadable<SparkCatalog>;
  duckdb: Loadable<DuckDBStatus>;
  docker: Loadable<DockerRuntimes>;
  prereqs: Prereqs | null;
  /** Versões Spark com instalação em andamento. */
  busyVersions: Set<string>;
  /** Versões DuckDB com instalação em andamento (além das que o backend lista em `installing`). */
  busyDuckDB: Set<string>;
  onInstall: (version: string) => Promise<void>;
  onInstallDuckDB: (version: string) => Promise<void>;
  /** Abre a janela de instalação do runtime Docker escolhido. */
  onInstallDocker: (runtime: DockerRuntime) => void;
  onReloadCatalog: () => void;
  /** Deep-link: pré-seleciona o item recomendado (primeiro instalável) da categoria. */
  target?: InstallTarget | null;
}

/** Opções do combo, na ordem das categorias; o primeiro habilitado de cada uma é o recomendado. */
function buildOptions(
  catalog: SparkCatalog | null,
  duckdb: DuckDBStatus | null,
  docker: DockerRuntimes | null,
  busyVersions: Set<string>,
  busyDuckDB: Set<string>,
): RuntimeOption[] {
  const out: RuntimeOption[] = [];
  for (const v of catalog?.versions ?? []) {
    const busy = busyVersions.has(v.version);
    out.push({
      id: `${SPARK}${v.version}`,
      category: "processing",
      label: `Spark ${v.version}`,
      description: formatDate(v.released_at),
      formats: v.formats ?? null,
      state: v.installed ? "installed" : busy ? "installing" : null,
      disabled: v.installed || busy,
    });
  }
  const duckdbInstalling = new Set((duckdb?.installing ?? []).filter((i) => i.kind === "duckdb-install").map((i) => i.kernel_name));
  for (const v of duckdb?.catalog ?? []) {
    const busy = busyDuckDB.has(v.version) || duckdbInstalling.has(duckdbKernelName(v.version));
    out.push({
      id: `${DUCKDB}${v.version}`,
      category: "analytics",
      label: `DuckDB ${v.version}`,
      description: duckdb?.supported ? v.extensions.join(" · ") : "not available on this platform",
      state: v.installed ? "installed" : busy ? "installing" : null,
      disabled: v.installed || busy || !duckdb?.supported,
    });
  }
  for (const r of docker?.runtimes ?? []) {
    out.push({
      id: `${DOCKER}${r.key}`,
      category: "docker",
      label: r.label,
      description: r.image,
      state: r.installed ? "installed" : r.busy ? "installing" : !r.available ? "unavailable" : null,
      disabled: r.installed || r.busy || !r.available,
    });
  }
  return out;
}

export function InstallPanel({ catalog, duckdb, docker, prereqs, busyVersions, busyDuckDB, onInstall, onInstallDuckDB, onInstallDocker, onReloadCatalog, target }: Props) {
  const options = useMemo(
    () => buildOptions(catalog.data, duckdb.data, docker.data, busyVersions, busyDuckDB),
    [catalog.data, duckdb.data, docker.data, busyVersions, busyDuckDB],
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Escolha que ficou indisponível (instalada, instalando) volta ao padrão: o Spark mais novo
  // ainda não instalado. A escolha do usuário é preservada enquanto continuar instalável.
  useEffect(() => {
    const current = options.find((o) => o.id === selected);
    if ((current && !current.disabled) || options.length === 0) return;
    setSelected(options.find((o) => o.category === "processing" && !o.disabled)?.id ?? null);
    // Só reage a novas opções (catálogos recarregados).
  }, [options]);

  // Deep-link: pré-seleciona o item recomendado da categoria. Só reage a um novo pedido (nonce);
  // quando ele chega, as listas já carregaram (o pai espera a primeira carga assentar).
  useEffect(() => {
    if (!target) return;
    const first = options.find((o) => o.category === target.category && !o.disabled);
    if (first) {
      setSelected(first.id);
      setError(null);
    }
  }, [target?.nonce]);

  const chosen = options.find((o) => o.id === selected) ?? null;
  const chosenDocker = chosen?.category === "docker" ? docker.data?.runtimes.find((r) => `${DOCKER}${r.key}` === chosen.id) : undefined;
  const sparkVersion = chosen?.id.startsWith(SPARK) ? chosen.id.slice(SPARK.length) : null;
  const duckdbVersion = chosen?.id.startsWith(DUCKDB) ? chosen.id.slice(DUCKDB.length) : null;
  const canInstall = !!chosen && !chosen.disabled && !submitting;
  const warn = sparkVersion ? jdkMissing(sparkVersion, prereqs) : null;
  const fallback = catalog.data && (catalog.data.fallback || catalog.data.source === "fallback");

  /** Handler do botão Install: é o único ponto que dispara instalação. */
  const submit = async () => {
    if (!chosen || chosen.disabled) return;
    setError(null);
    if (chosenDocker) {
      onInstallDocker(chosenDocker);
      return;
    }
    setSubmitting(true);
    try {
      if (sparkVersion) await onInstall(sparkVersion);
      else if (duckdbVersion) await onInstallDuckDB(duckdbVersion);
    } catch (err) {
      setError(installError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const allInstalled = options.length > 0 && options.every((o) => o.state === "installed");

  return (
    <div className={styles.block} data-testid="spark-install">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>Install</h3>
        <button type="button" className="btn btn-ghost" onClick={onReloadCatalog} disabled={catalog.loading}>
          {catalog.loading ? "Loading…" : "Refresh catalog"}
        </button>
      </div>
      <p className={styles.text}>
        {chosenDocker
          ? "Runs inside a Docker container; nothing is installed on this machine."
          : "Pick a runtime, then press Install. Only stable, complete releases are listed; installed ones are marked ✓."}
      </p>
      {fallback ? (
        <p className={styles.notice} data-testid="spark-catalog-fallback">
          {catalog.data?.source === "fallback"
            ? "PyPI unavailable — showing the known stable Spark versions."
            : "Some Spark lines could not be resolved on PyPI — showing their known stable versions."}
        </p>
      ) : null}
      {catalog.error ? <p className={styles.error}>Could not load the catalog: {catalog.error}</p> : null}
      {duckdb.error ? <p className={styles.error}>Could not load the DuckDB versions: {duckdb.error}</p> : null}
      {docker.error ? <p className={styles.error}>Could not load the Docker runtimes: {docker.error}</p> : null}
      <div className={styles.installRow}>
        <RuntimeCombo
          options={options}
          value={selected}
          disabled={options.length === 0}
          onChange={(id) => {
            setSelected(id);
            setError(null);
          }}
        />
        <button type="button" className="btn btn-primary" data-testid="spark-install-button" disabled={!canInstall} onClick={() => void submit()}>
          {submitting ? "Submitting…" : chosenDocker ? "Install…" : "Install"}
        </button>
      </div>
      {allInstalled ? <p className={styles.text}>All runtimes in the catalog are already installed.</p> : null}
      {warn ? <p className={styles.notice}>{warn}</p> : null}
      {error ? (
        <p className={styles.error} data-testid="spark-install-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
