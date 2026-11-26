/**
 * Painel Table info: encaixado à direita do conteúdo (não é modal), mostra os
 * metadados de `/api/catalog/table` da tabela aberta pela árvore do Catalog.
 * Só dados que não dependem do kernel; `history`/`stats` só no Iceberg, `properties` no Iceberg e no `glue`.
 * Tabelas do `glue` trazem ainda o armazenamento do AWS Glue (classification, formatos, SerDe); tipo, formato e
 * semântica do DROP chegam do backend como nos demais catálogos. Delta no `glue` guarda o schema no log Delta.
 * Moldura, abas, Esc e largura medida vêm do InfoPanelShell; ao fechar, o foco volta à linha da tabela.
 * Só no `spark_catalog`: "Remove from catalog" tira a tabela do registro (prévia → confirmação → DELETE com o etag),
 * sem apagar arquivos; ao concluir, fecha o painel e relê a árvore.
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  previewTableRemoval,
  removeTable,
  tableErrorCode,
  tableErrorMessage,
  tableReasonMessage,
  type GlueStorage,
  type RemoveEffect,
  type TableHistoryEntry,
  type TableInfo,
  type TableQuery,
  type TableRemovalPreview,
  type TableVersion,
} from "../../api/catalog";
import { TABLE_INFO_PANEL_ID, tableRef, useCatalog } from "../../state/catalog";
import { formatSize } from "../files/format";
import { ConfirmDialog } from "../shell/ConfirmDialog";
import { TableIcon } from "../shell/icons";
import { BrandIcon } from "./BrandIcon";
import { GLUE_CATALOG, SPARK_CATALOG } from "./catalogLabels";
import { DASH, Facts, InfoPanelShell } from "./InfoPanelShell";
import styles from "./InfoPanel.module.css";
import own from "./TableInfoPanel.module.css";
import { tableFormatIcon, tableFormatLabel } from "./tableFormat";

const DELTA_LOG_NOTE =
  "Delta table: the schema lives in the Delta log, not in the catalog. Only partition columns are listed here.";

/** Tabela cujo schema não está no catálogo (Delta registrada no `glue`): `columns` traz só as partições. */
function schemaInDeltaLog(info: TableInfo): boolean {
  return info.schema_source === "delta_log";
}

const METADATA_ERRORS: Record<string, string> = {
  unavailable: "Iceberg metadata unavailable — showing catalog registration only.",
  store_unavailable: "Notislake storage unavailable — showing catalog registration only.",
};

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "columns", label: "Columns" },
  { id: "history", label: "History" },
  { id: "properties", label: "Properties" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const dateFormat = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" });
const numberFormat = new Intl.NumberFormat("en-US");
/** ISO (ou epoch ms) → data legível; texto não reconhecido é exibido como veio. */
function formatDate(value: string | number | null): string {
  if (value === null || value === "") return DASH;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : dateFormat.format(d);
}

function formatCount(value: number | null): string {
  return value === null ? DASH : numberFormat.format(value);
}

function formatVersion(version: TableVersion | null): string {
  if (!version || version.value === null || version.value === "") return DASH;
  if (version.kind === "delta_version" || version.kind === "glue_version") return `version ${version.value}`;
  if (version.kind === "hudi_instant") return `instant ${version.value}`;
  return `snapshot ${version.value}`;
}

function TableFormatIcon({ format, size }: { format: string; size: number }) {
  const icon = tableFormatIcon(format);
  return icon ? <BrandIcon icon={icon} size={size} /> : <TableIcon size={size} />;
}

/**
 * Frase do DROP a partir de `drop_behavior`: só a gerenciada na própria pasta e sem outro uso enfileira a exclusão dos
 * arquivos; externa, gerenciada fora da própria pasta ou com a pasta compartilhada os preserva.
 */
function dropSentence(info: TableInfo): ReactNode {
  const where = info.location ? <code className={styles.mono}>{info.location}</code> : null;
  switch (info.drop_behavior) {
    case "deletes_files":
      return (
        <>
          Managed table: the catalog owns the data. DROP TABLE removes the registration and queues the files
          {where ? <> at {where}</> : null} for deletion.
        </>
      );
    case "registry_only":
      return (
        <>
          External table: the catalog only points to the files. DROP TABLE removes the registration; files stay
          {where ? <> at {where}</> : " in place"}.
        </>
      );
    case "keeps_files_outside_managed":
      return (
        <>
          Managed table outside its reserved folder. DROP TABLE removes the registration; files stay
          {where ? <> at {where}</> : " in place"}.
        </>
      );
    case "keeps_files_shared":
      return (
        <>
          Managed table whose folder is also used by another table. DROP TABLE removes the registration; files stay
          {where ? <> at {where}</> : " in place"}.
        </>
      );
    default:
      return null;
  }
}

function formatCompressed(value: boolean | null): string {
  return value === null ? DASH : value ? "yes" : "no";
}

/** Linhas do armazenamento do AWS Glue (só tabelas do catálogo `glue`). */
function glueFacts(glue: GlueStorage): [string, ReactNode][] {
  const mono = (v: string | null): ReactNode => (v ? <span className={styles.mono}>{v}</span> : DASH);
  return [
    ["Glue table type", glue.glue_table_type ?? DASH],
    ["Classification", glue.classification ?? DASH],
    ["Input format", mono(glue.input_format)],
    ["Output format", mono(glue.output_format)],
    ["SerDe", mono(glue.serde_library)],
    ["Compressed", formatCompressed(glue.compressed)],
  ];
}

function Overview({ info, onRemove }: { info: TableInfo; onRemove?: () => void }) {
  const facts: [string, ReactNode][] = [
    ["Full name", `${info.catalog}.${info.database}.${info.table}`],
    ["Type", info.table_type],
    ["Format", tableFormatLabel(info.format)],
    ["Location", info.location ?? DASH],
    ["Comment", info.description ? <span className={styles.prose}>{info.description}</span> : DASH],
    ["Partitions", info.partition_columns.length > 0 ? info.partition_columns.join(", ") : "None"],
    ["Columns", schemaInDeltaLog(info) ? "In the Delta log" : String(info.columns.length)],
    ["Registered at", formatDate(info.created_at)],
    ["Updated at", formatDate(info.updated_at)],
    ["Current version", formatVersion(info.version)],
  ];
  if (info.stats) {
    const size = info.stats.total_files_size;
    facts.push(
      ["Rows", formatCount(info.stats.total_records)],
      ["Size", size === null ? DASH : formatSize(size)],
      ["Data files", formatCount(info.stats.total_data_files)],
    );
  }
  if (info.glue) facts.push(...glueFacts(info.glue));
  return (
    <>
      <Facts facts={facts} />
      {onRemove ? (
        <p className={styles.note}>
          <button type="button" className="btn btn-danger" onClick={onRemove} data-testid="table-remove-from-catalog">
            Remove from catalog
          </button>
        </p>
      ) : null}
    </>
  );
}

function Columns({ info }: { info: TableInfo }) {
  if (info.columns.length === 0) {
    const text = schemaInDeltaLog(info) ? "No partition columns; the schema lives in the Delta log." : "No columns registered.";
    return <p className={styles.empty}>{text}</p>;
  }
  return (
    <table className={styles.grid}>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Name</th>
          <th scope="col">Type</th>
          <th scope="col">Nullable</th>
          <th scope="col">Comment</th>
        </tr>
      </thead>
      <tbody>
        {info.columns.map((c, i) => (
          <tr key={c.name}>
            <td className={styles.num}>{i + 1}</td>
            <td>
              {c.name}
              {c.is_partition ? <span className={styles.flag}>partition</span> : null}
            </td>
            <td>{c.data_type}</td>
            <td>{c.nullable ? "yes" : "no"}</td>
            {c.description ? (
              <td><span className={styles.prose}>{c.description}</span></td>
            ) : (
              <td className={styles.na}>{DASH}</td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function historyDetail(h: TableHistoryEntry): string {
  const keys = ["added-records", "deleted-records", "added-data-files"] as const;
  return keys
    .filter((k) => h.summary[k] !== undefined)
    .map((k) => `${k.replace(/-/g, " ")}: ${h.summary[k]}`)
    .join(" · ");
}

function History({ info }: { info: TableInfo }) {
  if (info.history === null) {
    if (info.catalog === GLUE_CATALOG) {
      return (
        <div className={styles.empty}>
          <p>Glue table version history is not shown; only the current version is known from the catalog.</p>
          <p>
            Current version: <span className={styles.mono}>{formatVersion(info.version)}</span>
          </p>
        </div>
      );
    }
    if (info.format === "parquet") return <p className={styles.empty}>Parquet has no versions.</p>;
    if (info.format === "iceberg") {
      return <p className={styles.empty}>Snapshot history unavailable without the Iceberg metadata.</p>;
    }
    return (
      <div className={styles.empty}>
        <p>
          {tableFormatLabel(info.format)} history needs the kernel; only the current version is known from the catalog.
        </p>
        <p>
          Current version: <span className={styles.mono}>{formatVersion(info.version)}</span>
        </p>
      </div>
    );
  }
  if (info.history.length === 0) return <p className={styles.empty}>No snapshots yet.</p>;
  const current = info.version?.value != null ? String(info.version.value) : null;
  return (
    <table className={styles.grid}>
      <thead>
        <tr>
          <th scope="col">Snapshot</th>
          <th scope="col">When</th>
          <th scope="col">Operation</th>
        </tr>
      </thead>
      <tbody>
        {info.history.map((h, i) => {
          const detail = historyDetail(h);
          const isCurrent = current !== null && h.id === current;
          return (
            <tr key={h.id ?? `row-${i}`} className={isCurrent ? own.current : undefined} aria-current={isCurrent || undefined}>
              <td className={styles.value} title={h.parent_id ? `parent ${h.parent_id}` : undefined}>
                {h.id ?? DASH}
                {isCurrent ? <span className={styles.flag}>current</span> : null}
              </td>
              <td>{formatDate(h.timestamp_ms)}</td>
              <td>
                {h.operation ?? DASH}
                {detail ? <div className={styles.sub}>{detail}</div> : null}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Properties({ info }: { info: TableInfo }) {
  if (info.properties === null) return <p className={styles.empty}>No properties available without the kernel.</p>;
  const entries = Object.entries(info.properties).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) return <p className={styles.empty}>No properties.</p>;
  return (
    <table className={styles.grid}>
      <thead>
        <tr>
          <th scope="col">Key</th>
          <th scope="col">Value</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td className={styles.value}>{k}</td>
            <td className={styles.value}>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Devolve o foco à linha da tabela na árvore do Catalog (se ainda estiver visível). */
function focusTreeRow(query: TableQuery) {
  const ref = tableRef(query);
  const rows = document.querySelectorAll<HTMLElement>('[role="treeitem"][data-table-ref]');
  for (const el of rows) {
    if (el.dataset.tableRef === ref) {
      el.focus();
      return;
    }
  }
}

const REMOVE_EFFECTS: Record<RemoveEffect, string> = {
  registry_only: "Removes only the catalog entry; files are kept.",
};

interface RemoveTableProps {
  query: TableQuery;
  onRemoved: () => void;
  onClose: () => void;
}

/**
 * Prévia → confirmação → DELETE com o etag; `catalog_changed` (ou `managed_use_drop` surgido depois da prévia) relê a
 * prévia e mantém o diálogo aberto, como a exclusão de schema.
 */
function RemoveTableDialog({ query, onRemoved, onClose }: RemoveTableProps) {
  const { catalog, database, table } = query;
  const [preview, setPreview] = useState<TableRemovalPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = useCallback((err: unknown) => {
    setError(tableErrorMessage(err));
    // Tabela sumiu: a árvore está defasada.
    if (tableErrorCode(err) === "table_not_found") useCatalog.getState().refresh();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    previewTableRemoval({ catalog, database, table }, ctrl.signal)
      .then(setPreview)
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted) fail(err);
      });
    return () => ctrl.abort();
  }, [catalog, database, table, fail]);

  async function confirm() {
    if (!preview) return;
    const target = { catalog, database, table };
    setBusy(true);
    setError(null);
    try {
      await removeTable(target, preview.etag);
    } catch (err) {
      const code = tableErrorCode(err);
      if (code === "catalog_changed" || code === "managed_use_drop") {
        try {
          setPreview(await previewTableRemoval(target));
          setError(tableErrorMessage(err));
        } catch (reread) {
          setPreview(null);
          fail(reread);
        }
      } else {
        fail(err);
      }
      setBusy(false);
      return;
    }
    onRemoved();
  }

  const blocked = preview !== null && !preview.can_remove;
  const shownError = error ?? (blocked ? tableReasonMessage(preview.reason) : null);
  const name = preview ? `${preview.database}.${preview.table}` : `${database}.${table}`;

  return (
    <ConfirmDialog
      title="Remove from catalog"
      confirmLabel="Remove"
      busyLabel="Removing…"
      danger
      busy={busy}
      confirmDisabled={preview === null || blocked}
      error={shownError}
      onConfirm={() => void confirm()}
      onCancel={onClose}
      testId="remove-table-dialog"
    >
      {preview || error ? (
        <p>
          Remove <code>{name}</code> from the catalog?
        </p>
      ) : (
        <p>Checking table…</p>
      )}
      {preview ? (
        <>
          <p>{REMOVE_EFFECTS[preview.remove_effect] ?? REMOVE_EFFECTS.registry_only}</p>
          <p>
            Location: {preview.location ? <code style={{ overflowWrap: "anywhere" }}>{preview.location}</code> : DASH}
          </p>
        </>
      ) : null}
    </ConfirmDialog>
  );
}

function PanelBody({ info, tab, onRemove }: { info: TableInfo; tab: TabId; onRemove?: () => void }) {
  switch (tab) {
    case "overview":
      return <Overview info={info} onRemove={onRemove} />;
    case "columns":
      return <Columns info={info} />;
    case "history":
      return <History info={info} />;
    case "properties":
      return <Properties info={info} />;
  }
}

export function TableInfoPanel() {
  const state = useCatalog((s) => (s.info?.kind === "table" ? s.info : null));
  const [removing, setRemoving] = useState<TableQuery | null>(null);
  if (!state) return null;
  const { query, data, loading, error } = state;
  const fullName = `${query.catalog}.${query.database}.${query.table}`;
  const format = data?.format ?? "";

  function close() {
    useCatalog.getState().closeInfo();
    focusTreeRow(query);
  }

  /** Remoção só do registro, oferecida apenas no `spark_catalog` (o backend recusa os demais). */
  const onRemove = data?.catalog === SPARK_CATALOG ? () => setRemoving(query) : undefined;

  function onRemoved() {
    setRemoving(null);
    const { closeInfo, refresh } = useCatalog.getState();
    // Fecha antes de reler: o `refresh()` relê o painel aberto, e a tabela não existe mais.
    closeInfo();
    refresh();
  }

  const metadataError = data?.metadata_error ? METADATA_ERRORS[data.metadata_error] : null;
  const notice = metadataError ?? (data && schemaInDeltaLog(data) ? DELTA_LOG_NOTE : null);

  return (
    <>
      <InfoPanelShell
        id={TABLE_INFO_PANEL_ID}
        label="Table info"
        testId="table-info-panel"
        resetKey={tableRef(query)}
        measureKey={data}
        icon={<TableFormatIcon format={format} size={18} />}
        title={data?.table ?? query.table}
        titleHint={query.table}
        path={fullName}
        loading={loading}
        error={error}
        hasData={data !== null}
        badges={
          data ? (
            <>
              <span className={`${styles.badge} ${data.table_type === "MANAGED" ? styles.managed : styles.external}`}>
                {data.table_type}
              </span>
              <span className={styles.badge}>{tableFormatLabel(data.format)}</span>
              {data.available === false ? <span className={`${styles.badge} ${styles.warn}`}>files missing</span> : null}
            </>
          ) : undefined
        }
        notices={
          notice ? (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          ) : null
        }
        callout={data ? dropSentence(data) : undefined}
        tabs={TABS}
        tablistLabel="Table info sections"
        renderTab={(tab) => (data ? <PanelBody info={data} tab={tab} onRemove={onRemove} /> : null)}
        onClose={close}
      />
      {removing ? <RemoveTableDialog query={removing} onRemoved={onRemoved} onClose={() => setRemoving(null)} /> : null}
    </>
  );
}
