/** Prerequisites da instalação: uv, Java/JDKs e compatibilidade por linha do Spark. */
import type { Prereqs } from "../../api/types";
import type { Loadable } from "./useSparkData";
import styles from "./Spark.module.css";

function Badge({ ok, label, testId }: { ok: boolean; label: string; testId: string }) {
  return (
    <span className={`${styles.badge} ${ok ? styles.badgeOk : styles.badgeBad}`} data-testid={testId} data-ok={ok}>
      <span aria-hidden="true">{ok ? "✓" : "✗"}</span> {label}
    </span>
  );
}

export function PrereqsPanel({ state, onReload }: { state: Loadable<Prereqs>; onReload: () => void }) {
  const p = state.data;
  return (
    <div className={styles.block} data-testid="spark-prereqs">
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>Prerequisites</h3>
        <button type="button" className="btn btn-ghost" onClick={onReload} disabled={state.loading}>
          {state.loading ? "Checking…" : "Check again"}
        </button>
      </div>
      {state.error ? <p className={styles.error}>Could not check: {state.error}</p> : null}
      {p ? (
        <>
          <dl className={styles.facts}>
            <dt>uv</dt>
            <dd>
              {p.uv.found ? (
                <span className={styles.mono}>{p.uv.version ?? "encontrado"}</span>
              ) : (
                <span className={styles.bad}>
                  not found — install with <code className={styles.code}>brew install uv</code>
                </span>
              )}
            </dd>
            <dt>Java</dt>
            <dd>
              {p.java.version ? <span className={styles.mono}>{p.java.version}</span> : <span className={styles.bad}>not found</span>}
              {p.java_home ? <span className={`${styles.mono} ${styles.subtle}`}> · {p.java_home}</span> : null}
            </dd>
            <dt>JDKs</dt>
            <dd>
              {p.java.jdks.length === 0 ? (
                <span className={styles.bad}>no JDK installed</span>
              ) : (
                <ul className={styles.jdks}>
                  {p.java.jdks.map((j) => (
                    <li key={j.home}>
                      <span className={styles.jdkVersion}>{j.version}</span>
                      <span className={`${styles.mono} ${styles.subtle}`}>{j.home}</span>
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </dl>
          <div className={styles.badges}>
            <Badge ok={p.java.spark3_ok} label="Spark 3.x: JDK 17" testId="prereq-spark3" />
            <Badge ok={p.java.spark4_ok} label="Spark 4.x: JDK 21/17" testId="prereq-spark4" />
          </div>
          {!p.java.spark3_ok ? (
            <p className={styles.hint}>
              Spark 3.x needs JDK 17: <code className={styles.code}>brew install --cask temurin@17</code>
            </p>
          ) : null}
          {!p.java.spark4_ok ? (
            <p className={styles.hint}>
              Spark 4.x uses JDK 21 (or 17): <code className={styles.code}>brew install --cask temurin@21</code>
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
