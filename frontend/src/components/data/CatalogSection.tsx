/**
 * Seção Catalog do painel Dados: catálogo → banco → tabela, lidos do
 * catálogo persistente (`catalog.db`), sem depender de kernel ou notebook.
 * Relê quando uma célula do notebook ativo volta a idle, no foco da janela e
 * pelo botão de refresh. Árvore ARIA plana, como em FileTree. Create Schema: botão
 * "+" do cabeçalho e menu de contexto do catálogo; Delete Schema no menu do schema, nos três catálogos
 * (`spark_catalog`, `iceberg` e `glue`). O `default` do `spark_catalog` e do `glue` é protegido.
 * Linha de tabela é folha (sem chevron): clique (ou Enter) abre o painel Table info, que mostra as colunas.
 * Linha de catálogo: clique (ou Enter) abre o painel Catalog info e expande o nó se recolhido (nunca recolhe);
 * o chevron (ou Space/setas) segue expandindo/recolhendo. Um painel lateral por vez.
 */
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { useStore } from "zustand";
import {
  deleteSchema,
  previewSchemaDeletion,
  schemaErrorCode,
  schemaErrorMessage,
  schemaReasonMessage,
  type CatalogNode,
  type CatalogTable,
  type SchemaDeletion,
  type SchemaPreview,
  type TableQuery,
} from "../../api/catalog";
import {
  CATALOG_INFO_PANEL_ID,
  openCatalogName,
  openTableQuery,
  sameTable,
  schemaKey,
  TABLE_INFO_PANEL_ID,
  tableRef,
  useCatalog,
} from "../../state/catalog";
import { activeNotebookPath, useRouter } from "../../state/router";
import { getEntry, useWorkspace, type NotebookEntry } from "../../state/workspace";
import {
  ChevronRightIcon,
  DatabaseIcon,
  ExternalTableIcon,
  FolderIcon,
  PlusIcon,
  RefreshIcon,
  TableIcon,
} from "../shell/icons";
import { ConfirmDialog } from "../shell/ConfirmDialog";
import { ContextMenu } from "../shell/ContextMenu";
import type { MenuItem } from "../shell/Menu";
import { BrandIcon } from "./BrandIcon";
import { catalogIcon, catalogLabel, GLUE_CATALOG, SPARK_CATALOG } from "./catalogLabels";
import { CardTitle } from "./CardTitle";
import { CreateSchemaDialog } from "./CreateSchemaDialog";
import styles from "./DataPanel.module.css";
import { INDENT_PX, treeIndent } from "./treeIndent";
import { tableFormatIcon } from "./tableFormat";

/** Espera depois de o kernel voltar a idle antes de reler o catálogo (evita varrer a cada célula). */
const REFRESH_DEBOUNCE_MS = 1500;
const NOTICE_MS = 8000;
const DEFAULT_SCHEMA = "default";

const CATALOG_ERRORS: Record<string, string> = {
  unsupported_iceberg_catalog_schema: "Iceberg tables unavailable: unsupported catalog schema.",
  iceberg_catalog_unreadable: "Iceberg tables unavailable: catalog could not be read.",
  glue_catalog_unreadable: "Glue tables unavailable: catalog could not be read.",
};

interface Row {
  key: string;
  kind: "catalog" | "schema" | "table";
  /** Nome real do catálogo (catálogo e schema). */
  catalog?: string;
  /** Nome real do schema (kind "schema"). */
  schema?: string;
  /** Leitura do catálogo falhou: não dá para criar schema nele. */
  catalogError?: boolean;
  parent: string | null;
  level: number;
  pos: number;
  size: number;
  label: string;
  detail?: string;
  title?: string;
  icon: ReactNode;
  /** Expansível (catálogo e banco; a tabela é folha). */
  expandable: boolean;
  /** Aberto na tela (expandido no estado do store). */
  open: boolean;
  /** Tabela cujos arquivos não existem mais. */
  unavailable?: boolean;
  table?: TableQuery;
}

type StatusRow = { status: true; key: string; level: number; text: string; error: boolean };
type Item = Row | StatusRow;

const isStatus = (i: Item): i is StatusRow => "status" in i;


/** Ícone da linha de catálogo na árvore: marca da tecnologia, ou pasta quando não há uma. */
function catalogRowIcon(name: string): ReactNode {
  const icon = catalogIcon(name);
  return icon ? <BrandIcon icon={icon} /> : <FolderIcon size={14} />;
}

function tableIcon(t: CatalogTable): ReactNode {
  const icon = tableFormatIcon(t.format);
  if (icon) return <BrandIcon icon={icon} />;
  return t.table_type.toUpperCase() === "EXTERNAL" ? <ExternalTableIcon size={14} /> : <TableIcon size={14} />;
}

function tableDetail(t: CatalogTable): string | undefined {
  return t.available === false ? "unavailable" : undefined;
}

function tableTitle(t: CatalogTable): string {
  const lines = [t.description ? `${t.name} · ${t.description}` : t.name];
  if (t.location) lines.push(t.location);
  if (t.available === false) lines.push("Files not found at this location.");
  return lines.join("\n");
}

function tableRows(
  catalog: string,
  tables: CatalogTable[],
  parent: string,
  level: number,
  database: string,
  out: Item[],
): void {
  tables.forEach((t, i) => {
    const key = `${parent}\u0000t:${t.name}`;
    out.push({
      key,
      kind: "table",
      parent,
      level,
      pos: i + 1,
      size: tables.length,
      label: t.name,
      detail: tableDetail(t),
      title: tableTitle(t),
      icon: tableIcon(t),
      expandable: false,
      open: false,
      unavailable: t.available === false,
      table: { catalog, database, table: t.name },
    });
  });
}

/** Árvore plana: catálogo → schema → tabela (folha), abrindo conforme `expanded` do store. */
function buildItems(catalogs: CatalogNode[], s: { expanded: Record<string, true> }): Item[] {
  const out: Item[] = [];

  catalogs.forEach((c, ci) => {
    const ckey = `c:${c.name}`;
    const cOpen = Boolean(s.expanded[ckey]);
    out.push({
      key: ckey,
      kind: "catalog",
      catalog: c.name,
      catalogError: Boolean(c.error),
      parent: null,
      level: 1,
      pos: ci + 1,
      size: catalogs.length,
      label: catalogLabel(c.name),
      detail: c.error ? "error" : undefined,
      icon: catalogRowIcon(c.name),
      expandable: true,
      open: cOpen,
    });
    if (!cOpen) return;
    if (c.error) {
      out.push({ status: true, key: `error:${ckey}`, level: 2, text: CATALOG_ERRORS[c.error] ?? "Catalog could not be read.", error: true });
    }
    const databases = c.databases;
    databases.forEach((d, di) => {
      const tables = d.tables;
      const dkey = schemaKey(c.name, d.name);
      const dOpen = Boolean(s.expanded[dkey]);
      out.push({ key: dkey, kind: "schema", catalog: c.name, schema: d.name, parent: ckey, level: 2, pos: di + 1, size: databases.length, label: d.name, icon: <DatabaseIcon size={14} />, expandable: true, open: dOpen });
      if (dOpen) {
        if (tables.length === 0) out.push({ status: true, key: `empty:${dkey}`, level: 3, text: "No tables", error: false });
        tableRows(c.name, tables, dkey, 3, d.name, out);
        if (d.truncated) {
          out.push({ status: true, key: `truncated:${dkey}`, level: 3, text: "Limited list: not all tables are shown.", error: false });
        }
      }
    });
  });
  return out;
}

function Empty({ title, hint, testId }: { title: string; hint?: string; testId?: string }) {
  return (
    <div className={styles.empty} data-testid={testId}>
      <div className={styles.emptyIcons} aria-hidden="true">
        <TableIcon size={18} />
        <TableIcon size={22} />
        <TableIcon size={18} />
      </div>
      <p>{title}</p>
      {hint ? <p className={styles.hint}>{hint}</p> : null}
    </div>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const KEPT_REASONS: Record<string, string> = {
  keeps_files_shared: "folder used by another table, files stay",
  keeps_files_outside_managed: "outside its managed folder, files stay",
  outside_warehouse: "local folder stays",
  no_deletion_queue: "deletion queue unavailable, files stay",
};

const keptLabel = (k: { table: string; reason: string }) => `${k.table} (${KEPT_REASONS[k.reason] ?? k.reason})`;

/** Aviso quando a exclusão enfileirou ou deixou arquivos, ou a pasta do schema; null se nada a dizer. */
function deletionNotice(schema: string, res: SchemaDeletion): string | null {
  const kept: string[] = [];
  const queued = res.files_queued.length;
  if (queued > 0) kept.push(`files of ${plural(queued, "managed table", "managed tables")} queued for deletion`);
  if (res.files_kept.length > 0) kept.push(`files kept for ${res.files_kept.map(keptLabel).join(", ")}`);
  if (res.folder_kept) kept.push("schema folder kept");
  return kept.length > 0 ? `Schema ${schema} deleted; ${kept.join("; ")}.` : null;
}

interface DeleteSchemaProps {
  catalog: string;
  schema: string;
  onDeleted: (res: SchemaDeletion) => void;
  onClose: () => void;
}

/** Prévia → confirmação → DELETE com o etag; `catalog_changed` relê a prévia e mantém o diálogo aberto. */
function DeleteSchemaDialog({ catalog, schema, onDeleted, onClose }: DeleteSchemaProps) {
  const [preview, setPreview] = useState<SchemaPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = useCallback((err: unknown) => {
    setError(schemaErrorMessage(err));
    // Schema sumiu: a árvore está defasada.
    if (schemaErrorCode(err) === "schema_not_found") useCatalog.getState().refresh();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    previewSchemaDeletion(catalog, schema, ctrl.signal)
      .then(setPreview)
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted) fail(err);
      });
    return () => ctrl.abort();
  }, [catalog, schema, fail]);

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      onDeleted(await deleteSchema(catalog, schema, preview.etag));
    } catch (err) {
      if (schemaErrorCode(err) === "catalog_changed") {
        try {
          setPreview(await previewSchemaDeletion(catalog, schema));
          setError(schemaErrorMessage(err));
        } catch (reread) {
          setPreview(null);
          fail(reread);
        }
      } else {
        fail(err);
      }
      setBusy(false);
    }
  }

  const blocked = preview !== null && !preview.can_delete;
  const shownError = error ?? (blocked ? schemaReasonMessage(preview.reason) : null);

  return (
    <ConfirmDialog
      title="Delete schema"
      confirmLabel="Delete"
      busyLabel="Deleting…"
      danger
      busy={busy}
      confirmDisabled={preview === null || blocked}
      error={shownError}
      onConfirm={() => void confirm()}
      onCancel={onClose}
      testId="delete-schema-dialog"
    >
      {preview ? (
        <>
          <p>
            Delete schema <code>{schema}</code> and its {plural(preview.tables, "table", "tables")}?
          </p>
          <p>
            {preview.managed_queued > 0
              ? `Files of ${plural(preview.managed_queued, "managed table", "managed tables")} will be queued for deletion; `
              : ""}
            {preview.managed_kept > 0
              ? `${plural(preview.managed_kept, "managed table folder stays", "managed table folders stay")}; `
              : ""}
            {plural(preview.external, "external table keeps", "external tables keep")} their files.
          </p>
          {catalog === "iceberg" && preview.views > 0 ? <p>{plural(preview.views, "view", "views")} will also be dropped.</p> : null}
          {catalog === GLUE_CATALOG && preview.can_delete ? (
            <p>
              Here, a managed table whose folder is used by another table keeps its files. A DROP from a notebook
              (Glue/Hive) behaves differently: DROP DATABASE refuses a schema with tables, and DROP TABLE deletes a
              managed table&apos;s folder even when another table uses it.
            </p>
          ) : null}
        </>
      ) : error ? (
        <p>
          Delete schema <code>{schema}</code>?
        </p>
      ) : (
        <p>Checking schema…</p>
      )}
    </ConfirmDialog>
  );
}

interface MenuState {
  x: number;
  y: number;
  row: Row;
  origin: HTMLElement | null;
}

function CatalogTree({ items, onCreate }: { items: Item[]; onCreate: (catalog: string) => void }) {
  const { toggle: storeToggle, expand: storeExpand, collapse, openInfo, openCatalogInfo } = useCatalog.getState();
  const toggle = (row: Row) => storeToggle(row.key);
  const infoQuery = useCatalog((s) => openTableQuery(s.info));
  const infoCatalog = useCatalog((s) => openCatalogName(s.info));
  /** Variante suave: abre o Catalog info e expande o nó se recolhido; nunca recolhe. */
  const openCatalog = (row: Row) => {
    if (!row.catalog) return;
    openCatalogInfo(row.catalog);
    if (!row.open) storeExpand(row.key);
  };
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [deleting, setDeleting] = useState<{ catalog: string; schema: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(t);
  }, [notice]);

  /** Itens do menu de contexto; tabelas não têm menu. */
  function menuItems(row: Row): MenuItem[] | null {
    if (row.kind === "catalog" && row.catalog) {
      const catalog = row.catalog;
      return [{ label: "Create Schema…", disabled: row.catalogError, onSelect: () => onCreate(catalog), testId: "catalog-create-schema" }];
    }
    if (row.kind === "schema" && row.catalog && row.schema) {
      const { catalog, schema } = row;
      const key = schema.toLowerCase();
      // Só o `default` do spark_catalog e do glue é protegido no backend (`cannot_drop_default`); os demais schemas,
      // inclusive bronze/silver/gold, são livres.
      const isProtected = (catalog === SPARK_CATALOG || catalog === GLUE_CATALOG) && key === DEFAULT_SCHEMA;
      return [{ label: "Delete Schema…", danger: true, disabled: isProtected, onSelect: () => setDeleting({ catalog, schema }), testId: "catalog-delete-schema" }];
    }
    return null;
  }

  function openMenuAtRow(row: Row) {
    const el = refs.current.get(row.key);
    if (!el || !menuItems(row)) return;
    const r = el.getBoundingClientRect();
    setMenu({ x: r.left + INDENT_PX, y: r.bottom, row, origin: el });
  }

  function onContextMenu(e: MouseEvent<HTMLDivElement>, row: Row) {
    if (!menuItems(row)) return;
    e.preventDefault();
    // Tecla ContextMenu em alguns navegadores gera o evento sem coordenadas.
    if (e.clientX === 0 && e.clientY === 0) openMenuAtRow(row);
    else setMenu({ x: e.clientX, y: e.clientY, row, origin: e.currentTarget });
  }

  function onDeleted(catalog: string, schema: string, res: SchemaDeletion) {
    const { forgetSchema, refresh } = useCatalog.getState();
    forgetSchema(catalog, schema);
    // Única releitura após a exclusão: árvore e o painel lateral aberto.
    refresh();
    setDeleting(null);
    setNotice(deletionNotice(schema, res));
  }
  const nav = items.filter((i): i is Row => !isStatus(i));
  const activeKey = nav.some((r) => r.key === focusKey) ? focusKey : (nav[0]?.key ?? null);
  const focusRow = (key: string | null | undefined) => {
    if (key) refs.current.get(key)?.focus();
  };

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>, row: Row, index: number) {
    switch (e.key) {
      case "ArrowDown":
        focusRow(nav[index + 1]?.key);
        break;
      case "ArrowUp":
        focusRow(nav[index - 1]?.key);
        break;
      case "Home":
        focusRow(nav[0]?.key);
        break;
      case "End":
        focusRow(nav[nav.length - 1]?.key);
        break;
      case "ArrowRight":
        if (row.expandable) {
          if (!row.open) storeExpand(row.key);
          else {
            const next = nav[index + 1];
            if (next && next.level > row.level) focusRow(next.key);
          }
        }
        break;
      case "ArrowLeft":
        if (row.expandable && row.open) collapse(row.key);
        else focusRow(row.parent);
        break;
      case "ContextMenu":
        openMenuAtRow(row);
        break;
      case "F10":
        if (!e.shiftKey) return;
        openMenuAtRow(row);
        break;
      case "Enter":
        if (row.kind === "table" && row.table) openInfo(row.table);
        else if (row.kind === "catalog" && row.catalog) openCatalog(row);
        else if (row.expandable) toggle(row);
        break;
      case " ":
        if (row.expandable) toggle(row);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  const menuList = menu ? menuItems(menu.row) : null;

  return (
    <>
    <div className={styles.treeBody} role="tree" aria-label="Catalog">
      {items.map((item) => {
        const indent = treeIndent(item.level);
        if (isStatus(item)) {
          return (
            <div key={item.key} role="presentation" className={`${styles.treeStatus} ${styles.treeGuides} ${item.error ? styles.treeError : ""}`} style={indent}>
              {item.text}
            </div>
          );
        }
        const index = nav.indexOf(item);
        const open = item.expandable && item.open;
        const isTable = item.kind === "table" && item.table !== undefined;
        const isCatalog = item.kind === "catalog" && item.catalog !== undefined;
        const infoOpen = (isTable && sameTable(item.table, infoQuery)) || (isCatalog && item.catalog === infoCatalog);
        return (
          <div
            key={item.key}
            ref={(el) => {
              if (el) refs.current.set(item.key, el);
              else refs.current.delete(item.key);
            }}
            role="treeitem"
            className={`${styles.treeRow} ${styles.treeGuides} ${item.unavailable ? styles.treeUnavailable : ""} ${infoOpen ? styles.openRow : ""}`}
            style={indent}
            aria-level={item.level}
            aria-posinset={item.pos}
            aria-setsize={item.size}
            aria-expanded={item.expandable ? open : undefined}
            aria-selected={item.key === focusKey}
            aria-controls={isTable && infoQuery ? TABLE_INFO_PANEL_ID : isCatalog && infoCatalog ? CATALOG_INFO_PANEL_ID : undefined}
            data-table-ref={isTable && item.table ? tableRef(item.table) : undefined}
            data-catalog-ref={isCatalog ? item.catalog : undefined}
            title={item.title ?? item.label}
            tabIndex={item.key === activeKey ? 0 : -1}
            onFocus={() => setFocusKey(item.key)}
            onKeyDown={(e) => onKeyDown(e, item, index)}
            onContextMenu={(e) => onContextMenu(e, item)}
            onClick={(e) => {
              setFocusKey(item.key);
              if (isTable && item.table) {
                e.currentTarget.focus();
                openInfo(item.table);
              } else if (isCatalog) {
                e.currentTarget.focus();
                openCatalog(item);
              } else if (item.expandable) toggle(item);
            }}
          >
            <span
              className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`}
              aria-hidden="true"
              onClick={
                isCatalog
                  ? (e) => {
                      // Chevron do catálogo só expande/recolhe; o resto da linha abre o Catalog info.
                      e.stopPropagation();
                      setFocusKey(item.key);
                      toggle(item);
                    }
                  : undefined
              }
            >
              {item.expandable ? <ChevronRightIcon size={12} /> : null}
            </span>
            <span className={styles.treeIcon}>{item.icon}</span>
            <span className={styles.treeName}>{item.label}</span>
            {item.detail ? <span className={styles.treeDetail}>{item.detail}</span> : null}
          </div>
        );
      })}
    </div>
    {menu && menuList ? (
      <ContextMenu
        x={menu.x}
        y={menu.y}
        items={menuList}
        ariaLabel={`Actions for ${menu.row.label}`}
        onClose={closeMenu}
        returnFocusTo={menu.origin}
      />
    ) : null}
    {deleting ? (
      <DeleteSchemaDialog
        catalog={deleting.catalog}
        schema={deleting.schema}
        onDeleted={(res) => onDeleted(deleting.catalog, deleting.schema, res)}
        onClose={() => setDeleting(null)}
      />
    ) : null}
    <div className={styles.catalogNotice} role="status" aria-live="polite">
      {notice}
    </div>
    </>
  );
}

/** Relê o catálogo quando o kernel do notebook ativo volta a idle (célula pode ter criado tabelas). */
function IdleRefresh({ entry }: { entry: NotebookEntry }) {
  const kernelState = useStore(entry.kernel, (s) => s.kernelState);
  useEffect(() => {
    if (kernelState !== "idle") return;
    const timer = setTimeout(() => {
      if (!document.hidden) useCatalog.getState().refresh();
    }, REFRESH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [kernelState]);
  return null;
}

function CatalogTitle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return <CardTitle id="data-catalog-title" label="Catalog" collapsed={collapsed} onToggle={onToggle} />;
}

/** Corpo do cartão: só monta expandido, então recolher também para a leitura no foco da janela e o refresh por idle. */
function CatalogBody({ onCreate }: { onCreate: (catalog: string) => void }) {
  const path = useRouter((s) => activeNotebookPath(s.route));
  useWorkspace((s) => s.tabs);
  const entry = path ? getEntry(path) : undefined;
  const data = useCatalog((s) => s.data);
  const error = useCatalog((s) => s.error);
  const expanded = useCatalog((s) => s.expanded);
  // O painel só monta depois de `bootstrapAuth()` "ok": a primeira leitura é segura aqui.
  useEffect(() => {
    useCatalog.getState().refresh();
    const onFocus = () => useCatalog.getState().refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const items = data ? buildItems(data.catalogs, { expanded }) : [];

  let body: ReactNode;
  if (!data) {
    body = error ? <p className={`${styles.hint} ${styles.treeError}`} role="alert">{error}</p> : <p className={styles.hint}>Loading…</p>;
  } else if (data.catalogs.length === 0) {
    body = <Empty title="No tables yet" hint="Spark tables will appear here." testId="catalog-empty" />;
  } else {
    body = (
      <div className={styles.tree}>
        {error ? <p className={`${styles.treeStatus} ${styles.treeError}`} role="alert">{error}</p> : null}
        <CatalogTree items={items} onCreate={onCreate} />
      </div>
    );
  }

  return (
    <>
      {entry ? <IdleRefresh key={entry.path} entry={entry} /> : null}
      {body}
    </>
  );
}

/** Destino do "+": spark_catalog quando legível; senão o primeiro catálogo sem erro. */
function defaultCreateTarget(catalogs: CatalogNode[] | undefined): string | null {
  const ok = (catalogs ?? []).filter((c) => !c.error);
  return (ok.find((c) => c.name === SPARK_CATALOG) ?? ok[0])?.name ?? null;
}

/**
 * Schemas do catálogo. No `spark_catalog` o `default` vazio fica oculto, mas sempre existe no backend: é incluído
 * para o diálogo recusá-lo.
 */
function existingSchemas(catalogs: CatalogNode[] | undefined, catalog: string): string[] {
  const spark = catalog === SPARK_CATALOG;
  const names = (catalogs ?? []).filter((c) => c.name === catalog).flatMap((c) => c.databases.map((d) => d.name));
  return spark && !names.some((n) => n.toLowerCase() === DEFAULT_SCHEMA) ? [...names, DEFAULT_SCHEMA] : names;
}

export function CatalogSection({ testId, collapsed, onToggle }: { testId?: string; collapsed: boolean; onToggle: () => void }) {
  const loading = useCatalog((s) => s.loading);
  const refresh = useCatalog((s) => s.refresh);
  const data = useCatalog((s) => s.data);
  const [createIn, setCreateIn] = useState<string | null>(null);
  const createTarget = defaultCreateTarget(data?.catalogs);

  function onCreated(catalog: string) {
    const { refresh: reload, expand } = useCatalog.getState();
    expand(`c:${catalog}`);
    reload();
  }

  return (
    <section
      className={`${styles.section} ${collapsed ? styles.sectionCollapsed : ""}`}
      data-testid={testId}
      aria-labelledby="data-catalog-title"
    >
      <div className={styles.sectionHeader}>
        <CatalogTitle collapsed={collapsed} onToggle={onToggle} />
        <div className={styles.sectionActions}>
          <button type="button" className="btn btn-ghost" onClick={refresh} disabled={loading} aria-label="Refresh catalog" title="Refresh">
            <RefreshIcon size={14} />
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            data-testid="catalog-add-schema"
            disabled={createTarget === null}
            onClick={() => createTarget && setCreateIn(createTarget)}
            aria-label="Create schema"
            title="Create schema"
          >
            <PlusIcon size={14} />
          </button>
        </div>
      </div>
      {collapsed ? null : <CatalogBody onCreate={setCreateIn} />}
      {createIn ? (
        <CreateSchemaDialog
          catalog={createIn}
          catalogLabel={catalogLabel(createIn)}
          existing={existingSchemas(data?.catalogs, createIn)}
          onCreated={() => onCreated(createIn)}
          onClose={() => setCreateIn(null)}
        />
      ) : null}
    </section>
  );
}
