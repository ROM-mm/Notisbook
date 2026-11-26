/**
 * Painel Catalog info: aberto pelo nome do catálogo na árvore do Catalog, mostra `/api/catalog/info`
 * (contagens do `catalog.db` e a config do perfil Spark local, já mascarada no backend). Só leitura,
 * sem kernel.
 * Moldura, abas, Esc e largura medida vêm do InfoPanelShell; ao fechar, o foco volta à linha do catálogo.
 */
import type { ReactNode } from "react";
import type { CatalogInfo, CatalogInfoStatus, CatalogKind } from "../../api/catalog";
import { CATALOG_INFO_PANEL_ID, useCatalog } from "../../state/catalog";
import { DatabaseIcon } from "../shell/icons";
import { BrandIcon } from "./BrandIcon";
import { catalogIcon, catalogLabel, GLUE_CATALOG } from "./catalogLabels";
import { DASH, Facts, InfoPanelShell } from "./InfoPanelShell";
import styles from "./InfoPanel.module.css";
import { tableFormatLabel } from "./tableFormat";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "config", label: "Config" },
  { id: "namespaces", label: "Namespaces" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const KIND_LABELS: Record<CatalogKind, string> = {
  session: "session catalog",
  named: "named catalog",
};

const STATUS_LABELS: Record<CatalogInfoStatus, string> = {
  ok: "ok",
  empty: "empty — catalog database not created yet",
  unsupported_iceberg_catalog_schema: "unavailable",
  iceberg_catalog_unreadable: "unavailable",
};

/** Mesmo texto da árvore do Catalog para o Iceberg degradado. */
const STATUS_ERRORS: Partial<Record<CatalogInfoStatus, string>> = {
  unsupported_iceberg_catalog_schema: "Iceberg tables unavailable: unsupported catalog schema.",
  iceberg_catalog_unreadable: "Iceberg tables unavailable: catalog could not be read.",
};

const PROFILE_NOTE =
  "Config shown is the local Spark runtime profile. In Docker/Glue and DuckDB runtimes, iceberg is reached through the app's REST catalog and the token is applied to the session.";

const GLUE_NOTE =
  "Local AWS Glue Data Catalog served by the app. Glue runtimes reach it through the AWS Glue API endpoint; schemas and tables are created from notebooks, not from this panel.";

/** Nota de rodapé do Overview por catálogo. */
function profileNote(name: string): string {
  return name === GLUE_CATALOG ? GLUE_NOTE : PROFILE_NOTE;
}

const numberFormat = new Intl.NumberFormat("en-US");

function CatalogIcon({ name, size }: { name: string; size: number }) {
  const icon = catalogIcon(name);
  return icon ? <BrandIcon icon={icon} size={size} /> : <DatabaseIcon size={size} />;
}

/** Caminho do cabeçalho: chave de config do catálogo, ou o Glue local. */
function catalogPath(name: string): string {
  if (name === GLUE_CATALOG) return `${GLUE_CATALOG} · AWS Glue Data Catalog`;
  return `spark.sql.catalog.${name}`;
}

function formatsText(formats: Record<string, number>): string {
  const entries = Object.entries(formats).filter(([, n]) => n > 0);
  if (entries.length === 0) return "None";
  return entries
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([f, n]) => `${tableFormatLabel(f)} ${numberFormat.format(n)}`)
    .join(", ");
}

function Overview({ info }: { info: CatalogInfo }) {
  const facts: [string, ReactNode][] = [
    ["Status", STATUS_LABELS[info.status] ?? info.status],
    ["Kind", KIND_LABELS[info.kind] ?? info.kind],
  ];
  if (info.backing_catalog) facts.push(["Backing catalog", info.backing_catalog]);
  facts.push(
    ["Implementation", info.implementation ?? DASH],
    ["Type", info.type ?? DASH],
    ["Warehouse", info.warehouse ?? DASH],
    ["URI", info.uri ?? DASH],
    ["FileIO", info.file_io ?? DASH],
    ["Namespaces", numberFormat.format(info.counts.namespaces)],
    ["Tables", numberFormat.format(info.counts.tables)],
    ["Views", numberFormat.format(info.counts.views)],
    ["Formats", formatsText(info.formats)],
  );
  return (
    <>
      <Facts facts={facts} />
      <p className={styles.note}>{profileNote(info.name)}</p>
    </>
  );
}

function Config({ info }: { info: CatalogInfo }) {
  if (info.config.length === 0) {
    return <p className={styles.note}>No catalog configuration for the {info.profile} profile.</p>;
  }
  return (
    <table className={styles.grid}>
      <thead>
        <tr>
          <th scope="col">Key</th>
          <th scope="col">Value</th>
        </tr>
      </thead>
      <tbody>
        {info.config.map((c) => (
          <tr key={c.key}>
            <td className={styles.value}>{c.key}</td>
            <td className={styles.value}>
              {c.value}
              {c.redacted ? <span className={styles.flag}>redacted</span> : null}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Namespaces({ info }: { info: CatalogInfo }) {
  if (info.namespaces.length === 0) return <p className={styles.empty}>No namespaces in this node.</p>;
  return (
    <>
      <p className={styles.note}>Tables and views in this node.</p>
      <table className={styles.grid}>
        <thead>
          <tr>
            <th scope="col">Namespace</th>
            <th scope="col">Tables</th>
            <th scope="col">Views</th>
          </tr>
        </thead>
        <tbody>
          {info.namespaces.map((n) => (
            <tr key={n.name}>
              <td className={styles.value}>{n.name}</td>
              <td className={styles.value}>{numberFormat.format(n.tables)}</td>
              <td className={styles.value}>{numberFormat.format(n.views)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {info.namespaces_truncated ? (
        <p className={styles.note}>Limited list: not all namespaces are shown.</p>
      ) : null}
    </>
  );
}

function PanelBody({ info, tab }: { info: CatalogInfo; tab: TabId }) {
  switch (tab) {
    case "overview":
      return <Overview info={info} />;
    case "config":
      return <Config info={info} />;
    case "namespaces":
      return <Namespaces info={info} />;
  }
}

/** Devolve o foco à linha do catálogo na árvore do Catalog (se ainda estiver visível). */
function focusCatalogRow(name: string) {
  const rows = document.querySelectorAll<HTMLElement>('[role="treeitem"][data-catalog-ref]');
  for (const el of rows) {
    if (el.dataset.catalogRef === name) {
      el.focus();
      return;
    }
  }
}

export function CatalogInfoPanel() {
  const state = useCatalog((s) => (s.info?.kind === "catalog" ? s.info : null));
  if (!state) return null;
  const { name, data, loading, error } = state;
  const statusError = data ? STATUS_ERRORS[data.status] : undefined;

  function close() {
    useCatalog.getState().closeInfo();
    focusCatalogRow(name);
  }

  return (
    <InfoPanelShell
      id={CATALOG_INFO_PANEL_ID}
      label="Catalog info"
      testId="catalog-info-panel"
      resetKey={name}
      measureKey={data}
      icon={<CatalogIcon name={name} size={18} />}
      title={catalogLabel(name)}
      titleHint={name}
      path={catalogPath(name)}
      loading={loading}
      error={error}
      hasData={data !== null}
      badges={
        data ? (
          <>
            <span className={styles.badge}>{KIND_LABELS[data.kind] ?? data.kind}</span>
            <span className={styles.badge}>profile: {data.profile}</span>
            {data.status === "empty" ? <span className={`${styles.badge} ${styles.warn}`}>empty</span> : null}
          </>
        ) : undefined
      }
      notices={
        statusError ? (
          <p className={`${styles.notice} ${styles.error}`} role="alert">
            {statusError}
          </p>
        ) : null
      }
      tabs={TABS}
      tablistLabel="Catalog info sections"
      renderTab={(tab) => (data ? <PanelBody info={data} tab={tab} /> : null)}
      onClose={close}
    />
  );
}
