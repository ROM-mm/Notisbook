/**
 * Raiz da aplicação: autentica (cookie via `?token=`) e monta o layout
 * (`AppShell`: header, abas, painel lateral, conteúdo).
 *
 * Conteúdo por rota (`state/router.ts`):
 * - "files"    → início (nenhum notebook ativo); `/tree/<dir>` abre o painel
 *                Notebooks com a árvore expandida até <dir>
 * - "notebook" → aba do notebook (abre se preciso) com components/kernel/NotebookPage
 * - "settings" → components/settings/SettingsPage ("Ambientes Spark")
 */
import { type ComponentType, lazy, Suspense, useEffect, useState } from "react";
import { bootstrapAuth, errorMessage } from "./api";
import { AppShell } from "./components/shell/AppShell";
import shellStyles from "./components/shell/AppShell.module.css";
import { DeltaIcon, FileParquetIcon, HudiIcon, IcebergIcon } from "./components/shell/icons";
import { Placeholder, StatusScreen } from "./components/shell/StatusScreen";
import { SettingsPage } from "./components/settings/SettingsPage";
import { getTargetDir, useNotebookTree } from "./state/notebookTree";
import { useFiles } from "./state/files";
import { type Route, useRouter } from "./state/router";
import { useSystemResources } from "./state/systemResources";
import { createUntitledNotebook, getEntry, useWorkspace } from "./state/workspace";

/** Editor (CodeMirror + markdown + saídas/kernel) em chunk separado: só carrega ao abrir um notebook. */
const NotebookPage = lazy(() =>
  import("./components/kernel/NotebookPage").then((m) => ({ default: m.NotebookPage })),
);

type Boot = { status: "loading" } | { status: "ready" } | { status: "unauthorized" } | { status: "error"; message: string };

export function App() {
  const [boot, setBoot] = useState<Boot>({ status: "loading" });
  const route = useRouter((s) => s.route);

  useEffect(() => {
    let cancelled = false;
    bootstrapAuth()
      .then(async (r) => {
        if (cancelled) return;
        if (r === "ok") {
          useFiles.getState().loadRoot();
          useSystemResources.getState().start();
          // Raiz e geração entram antes de liberar a UI: o primeiro request já envia a geração.
          await useWorkspace.getState().loadRoot();
          if (cancelled) return;
        }
        setBoot(r === "ok" ? { status: "ready" } : { status: "unauthorized" });
      })
      .catch((err: unknown) => !cancelled && setBoot({ status: "error", message: errorMessage(err) }));
    return () => {
      cancelled = true;
      useSystemResources.getState().stop();
    };
  }, []);

  switch (boot.status) {
    case "loading":
      return <StatusScreen title="Notisbook">Connecting to server…</StatusScreen>;
    case "unauthorized":
      return (
        <StatusScreen title="Unauthorized access">
          Open the address printed by the server in the terminal (with <code>?token=…</code>) to sign in.
        </StatusScreen>
      );
    case "error":
      return <StatusScreen title="Server unavailable">{boot.message}</StatusScreen>;
    case "ready":
      return <Workspace route={route} />;
  }
}

const FORMATS: { name: string; Icon: ComponentType<{ size?: number }> }[] = [
  { name: "Iceberg", Icon: IcebergIcon },
  { name: "Delta", Icon: DeltaIcon },
  { name: "Hudi", Icon: HudiIcon },
  { name: "Parquet", Icon: FileParquetIcon },
];

function Home() {
  const setExplorerOpen = useWorkspace((s) => s.setExplorerOpen);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className={shellStyles.home}>
      <h2 className={shellStyles.homeHero}>
        <span className={shellStyles.homeMark}>Spark it up locally.</span>
      </h2>
      <p className={shellStyles.homeSub}>Iceberg, Delta, Hudi &amp; Parquet — on your laptop.</p>
      <ul className={shellStyles.homeFormats} aria-label="Supported table formats">
        {FORMATS.map(({ name, Icon }) => (
          <li key={name} className={shellStyles.homeFormat}>
            <Icon size={32} />
            <span>{name}</span>
          </li>
        ))}
      </ul>
      <div className={shellStyles.homeActions}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() =>
            void createUntitledNotebook(getTargetDir()).catch((err: unknown) => setError(errorMessage(err)))
          }
        >
          New notebook
        </button>
        <button type="button" className="btn" onClick={() => setExplorerOpen(true)}>
          Open Explorer
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}

function Workspace({ route }: { route: Route }) {
  const ensureTab = useWorkspace((s) => s.ensureTab);
  const tabs = useWorkspace((s) => s.tabs);

  // A rota define a aba ativa (abre a aba se preciso) e até onde a árvore do painel se expande.
  useEffect(() => {
    if (route.view === "notebook") ensureTab(route.path);
    else if (route.view === "files" && route.dir) {
      useNotebookTree.getState().expandTo(route.dir);
      useWorkspace.getState().setExplorerOpen(true);
    }
  }, [route, ensureTab]);

  const entry = route.view === "notebook" && tabs.includes(route.path) ? (getEntry(route.path) ?? null) : null;

  let content;
  if (route.view === "settings") {
    content = <SettingsPage />;
  } else if (route.view === "notebook") {
    content = entry ? (
      <Suspense fallback={<Placeholder title="Notisbook">Opening editor…</Placeholder>}>
        <NotebookPage key={entry.path} entry={entry} />
      </Suspense>
    ) : null;
  } else {
    content = <Home />;
  }

  return <AppShell entry={entry}>{content}</AppShell>;
}
