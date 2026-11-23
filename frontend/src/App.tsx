/**
 * Raiz da aplicação: autentica (cookie via `?token=`) e monta o layout
 * (`AppShell`: header, abas, painel lateral, conteúdo).
 *
 * Conteúdo por rota (`state/router.ts`):
 * - "files"    → sem abas e fora de `browsing`: início limpo (marca, Get started sem runtime,
 *                Examples, ações, Your notebooks), SEM `AppShell`; `/tree/<dir>` idem. Com abas abertas: `AppShell`
 *                com o início no centro. `browsing` sem abas: `AppShell` com painel Notebooks e centro vazio
 * - "notebook" → aba do notebook (abre se preciso) com components/kernel/NotebookPage
 * - "settings" → components/settings/SettingsPage ("Runtimes")
 * - "appearance" → components/appearance/AppearancePage (fontes; ⌘, abre de qualquer tela)
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { bootstrapAuth, errorMessage, type Kernelspec, listKernelspecs, type Sample } from "./api";
import { isMac } from "./components/shell/platform";
import { AppShell } from "./components/shell/AppShell";
import shellStyles from "./components/shell/AppShell.module.css";
import { HomeBrandMark } from "./components/shell/icons";
import { Placeholder, StatusScreen } from "./components/shell/StatusScreen";
import { AppearancePage } from "./components/appearance/AppearancePage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { joinPath, notebookTitle } from "./lib/paths";
import { useRecent } from "./state/recent";
import { useFiles } from "./state/files";
import { useNotebookTree } from "./state/notebookTree";
import { openAppearance, openNotebook, openSettings, type Route, useRouter } from "./state/router";
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

  // ⌘, (Ctrl+, fora do Mac) abre Appearance de qualquer tela (inclusive o início, sem AppShell).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = isMac() ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (e.key !== "," || !mod || e.altKey || e.shiftKey) return;
      e.preventDefault();
      if (!e.repeat) openAppearance();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
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

/** `null` enquanto carrega; falha de rede vira `[]` (a seção some, a home segue de pé). */
type Loaded<T> = T[] | null;

/** Rótulo do motor do exemplo (cabeçalho do card). */
function engineLabel(sample: Sample): string {
  if (sample.runtime_kind === "duckdb") return "DuckDB";
  if (sample.runtime_kind === "local") return "Spark";
  return /glue/i.test(`${sample.kernel_name} ${sample.display_name}`) ? "AWS Glue" : "Docker";
}

/**
 * Kernelspecs instalados, buscados uma vez na montagem da Home (não dependem da raiz).
 * Falha liga `specsFailed` (status dos runtimes desconhecido).
 */
function useKernelspecs(): { specs: Loaded<Kernelspec>; specsFailed: boolean } {
  const [specs, setSpecs] = useState<Loaded<Kernelspec>>(null);
  const [specsFailed, setSpecsFailed] = useState(false);
  useEffect(() => {
    const ctrl = new AbortController();
    listKernelspecs(ctrl.signal)
      .then((list) => {
        setSpecsFailed(false);
        setSpecs(list);
      })
      .catch(() => {
        if (ctrl.signal.aborted) return;
        setSpecsFailed(true);
        setSpecs([]);
      });
    return () => ctrl.abort();
  }, []);
  return { specs, specsFailed };
}

/** `embedded`: dentro do `<main>` do AppShell (evita `<main>` aninhado). */
function Home({ dir, embedded = false }: { dir: string; embedded?: boolean }) {
  const Root = embedded ? "div" : "main";
  const recent = useRecent((s) => s.paths);
  const recentRoot = useRecent((s) => s.root);
  const samplePaths = useRecent((s) => s.samplePaths);
  const [error, setError] = useState<string | null>(null);
  // Exemplos vêm do workspace, a mesma busca que preenche `samplePaths` (sem corrida com o filtro).
  const samples = useWorkspace((s) => s.samples);
  const { specs, specsFailed } = useKernelspecs();

  // Só decide o layout com as duas respostas em mãos (sem piscar o "Get started").
  const ready = samples !== null && specs !== null;
  const installed = new Set((specs ?? []).map((k) => k.name));
  // Sem kernelspecs (erro), não mostra o setup: as ações seguem acessíveis.
  const needsSetup = ready && !specsFailed && installed.size === 0;
  const mine = recent.filter((p) => !samplePaths.has(p));

  const newNotebook = () => {
    setError(null);
    void createUntitledNotebook(dir).catch((err: unknown) => setError(errorMessage(err)));
  };
  const openSample = (sample: Sample) => {
    setError(null);
    // Status desconhecido (erro nos kernelspecs): abre; o kernel reporta o que faltar.
    if (specsFailed || installed.has(sample.kernel_name)) {
      useWorkspace.getState().showPanels();
      openNotebook(sample.path);
    } else openSettings(sample.runtime_kind);
  };

  return (
    <Root className={shellStyles.home}>
      <div className={shellStyles.homeBrand}>
        <HomeBrandMark size={112} />
        <div className={shellStyles.homeBrandText}>
          <h2 className={shellStyles.homeName}>notisbook</h2>
          <p className={shellStyles.homeTagline}>Process anything. Locally.</p>
        </div>
      </div>

      {needsSetup ? (
        <section className={shellStyles.homeSection} aria-labelledby="home-setup-h">
          <div className={shellStyles.homeSectionHead}>
            <h3 id="home-setup-h">Get started</h3>
            <span>2 steps</span>
          </div>
          <div className={shellStyles.homeSetup}>
            <div className={shellStyles.homeStep}>
              <span className={shellStyles.homeStepNumber} aria-hidden="true">
                1
              </span>
              <div>
                <h4>Install a runtime</h4>
                <p>Pick an engine — Spark, AWS Glue or DuckDB — and install it once.</p>
                <button type="button" className={`btn btn-primary ${shellStyles.homeBtnSm}`} onClick={() => openSettings()}>
                  Open Runtimes
                </button>
              </div>
            </div>
            <div className={shellStyles.homeStep}>
              <span className={shellStyles.homeStepNumber} aria-hidden="true">
                2
              </span>
              <div>
                <h4>Open a notebook</h4>
                <p>Start from one of the examples below or create a blank notebook.</p>
                <button type="button" className={`btn ${shellStyles.homeBtnSm}`} onClick={newNotebook}>
                  New notebook
                </button>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {ready && samples.length > 0 ? (
        <section className={shellStyles.homeSection} aria-labelledby="home-examples-h">
          <div className={shellStyles.homeSectionHead}>
            <h3 id="home-examples-h">Examples</h3>
            <span>open a ready-made notebook</span>
          </div>
          <div className={shellStyles.homeExamples}>
            {samples.map((sample) => {
              const ok = specsFailed || installed.has(sample.kernel_name);
              const runtimeLabel = sample.display_name || sample.kernel_name;
              const fullPath = recentRoot ? joinPath(recentRoot, sample.path) : sample.path;
              return (
                <button
                  key={sample.path}
                  type="button"
                  className={shellStyles.homeExample}
                  title={ok ? fullPath : `Needs ${runtimeLabel} — opens Runtimes`}
                  onClick={() => openSample(sample)}
                >
                  <span className={shellStyles.homeExampleEngine}>{engineLabel(sample)}</span>
                  <span className={shellStyles.homeExampleName}>{sample.name}</span>
                  <span className={shellStyles.homeExampleNeed}>
                    <i
                      role="img"
                      className={
                        specsFailed
                          ? shellStyles.homeDot
                          : `${shellStyles.homeDot} ${installed.has(sample.kernel_name) ? shellStyles.homeDotOk : shellStyles.homeDotOff}`
                      }
                      aria-label={
                        specsFailed
                          ? "Runtime status unknown"
                          : installed.has(sample.kernel_name)
                            ? "Runtime installed"
                            : "Runtime not installed"
                      }
                    />
                    {runtimeLabel}
                  </span>
                  <span className={shellStyles.homeExampleGo}>{ok ? "Open →" : "Install runtime →"}</span>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      {ready && !needsSetup ? (
        <div className={shellStyles.homeActions}>
          <button type="button" className="btn btn-primary" onClick={newNotebook}>
            New notebook
          </button>
          <button type="button" className="btn" onClick={() => openSettings()}>
            Runtimes
            {specsFailed ? null : <span className={shellStyles.homeRuntimeChip}>· {installed.size} installed</span>}
          </button>
        </div>
      ) : null}

      {ready ? (
        <section className={shellStyles.homeSection} aria-labelledby="home-mine-h">
          <div className={shellStyles.homeSectionHead}>
            <h3 id="home-mine-h">Your notebooks</h3>
            <span>most recent first</span>
          </div>
          {mine.length > 0 ? (
            <ul className={shellStyles.homeRecent} aria-label="Recent notebooks">
              {mine.map((path) => {
                const fullPath = recentRoot ? joinPath(recentRoot, path) : path;
                return (
                  <li key={path}>
                    <button
                      type="button"
                      className={shellStyles.homeRecentItem}
                      title={fullPath}
                      onClick={() => {
                        setError(null);
                        useWorkspace.getState().showPanels();
                        openNotebook(path);
                      }}
                    >
                      <span className={shellStyles.homeRecentName}>{notebookTitle(path)}</span>
                      <span className={shellStyles.homeRecentPath}>
                        <bdi>{fullPath}</bdi>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className={shellStyles.homeEmpty}>No notebooks yet. Examples don't show up here — only notebooks you create.</p>
          )}
        </section>
      ) : null}

      <button type="button" className={shellStyles.homeBrowse} onClick={() => useWorkspace.getState().startBrowsing(dir)}>
        Browse notebooks…
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </Root>
  );
}

function Workspace({ route }: { route: Route }) {
  const ensureTab = useWorkspace((s) => s.ensureTab);
  const tabs = useWorkspace((s) => s.tabs);
  const browsing = useWorkspace((s) => s.browsing);

  // A rota define a aba ativa (abre a aba se preciso).
  useEffect(() => {
    if (route.view === "notebook") ensureTab(route.path);
  }, [route, ensureTab]);

  // Abertura direta em `/tree/<dir>`: deixa a árvore expandida até `<dir>` (só no carregamento).
  useEffect(() => {
    const initial = useRouter.getState().route;
    if (initial.view === "files" && initial.dir) useNotebookTree.getState().expandTo(initial.dir);
  }, []);

  // `browsing` só vale na rota `files`; ao sair dela, não pode ficar preso.
  useEffect(() => {
    if (route.view !== "files" && browsing) useWorkspace.setState({ browsing: false });
  }, [route.view, browsing]);

  // Início limpo (sem AppShell) só sem abas e fora da navegação.
  if (route.view === "files" && tabs.length === 0 && !browsing) return <Home dir={route.dir} />;

  const entry = route.view === "notebook" && tabs.includes(route.path) ? (getEntry(route.path) ?? null) : null;

  let content;
  if (route.view === "settings") {
    content = <SettingsPage />;
  } else if (route.view === "appearance") {
    content = <AppearancePage />;
  } else if (route.view === "files") {
    content = tabs.length > 0 ? <Home dir={route.dir} embedded /> : null;
  } else {
    content = entry ? (
      <Suspense fallback={<Placeholder title="Notisbook">Opening editor…</Placeholder>}>
        <NotebookPage key={entry.path} entry={entry} />
      </Suspense>
    ) : null;
  }

  return <AppShell entry={entry}>{content}</AppShell>;
}
