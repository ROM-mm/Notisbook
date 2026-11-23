/**
 * Roteamento mínimo por History API (sem biblioteca). A rota define o
 * conteúdo da área principal:
 *   /                      → início (nenhum notebook ativo)
 *   /tree/<dir>            → início; a árvore de Notebooks é expandida até <dir> (abertura direta e Browse)
 *   /notebooks/<path>      → aba do notebook <path> ativa (abre a aba se preciso)
 *   /settings/appearance   → Settings › Appearance (fontes)
 *   /settings              → Settings (gestão do Spark); `/spark` é alias legado
 *   /settings?runtime=<k>  → idem, rolando/destacando a seção do runtime <k> (local|docker|duckdb)
 * Em produção o FastAPI devolve index.html para essas rotas (fallback SPA).
 */
import { create } from "zustand";

/** Runtime alvo da tela Runtimes (vocabulário do backend). */
export type RuntimeKind = "local" | "docker" | "duckdb";

const RUNTIME_KINDS: readonly RuntimeKind[] = ["local", "docker", "duckdb"];

export function isRuntimeKind(value: unknown): value is RuntimeKind {
  return typeof value === "string" && (RUNTIME_KINDS as readonly string[]).includes(value);
}

export type Route =
  | { view: "files"; dir: string }
  | { view: "notebook"; path: string }
  | { view: "settings"; runtime?: RuntimeKind }
  | { view: "appearance" };

function decodeRest(pathname: string, prefix: string): string {
  return pathname
    .slice(prefix.length)
    .split("/")
    .filter(Boolean)
    .map((s) => {
      try {
        return decodeURIComponent(s);
      } catch {
        return s;
      }
    })
    .join("/");
}

function encodeRest(path: string): string {
  return path.split("/").filter(Boolean).map(encodeURIComponent).join("/");
}

function isUnder(pathname: string, base: string): boolean {
  return pathname === base || pathname.startsWith(`${base}/`);
}

/** Lê `?runtime=` da query; valor ausente ou desconhecido vira `undefined`. */
function parseRuntime(search: string): RuntimeKind | undefined {
  const value = new URLSearchParams(search).get("runtime");
  return isRuntimeKind(value) ? value : undefined;
}

export function parseRoute(pathname: string, search = ""): Route {
  if (pathname.startsWith("/notebooks/")) return { view: "notebook", path: decodeRest(pathname, "/notebooks/") };
  if (isUnder(pathname, "/settings/appearance")) return { view: "appearance" };
  if (isUnder(pathname, "/settings") || isUnder(pathname, "/spark")) {
    const runtime = parseRuntime(search);
    return runtime ? { view: "settings", runtime } : { view: "settings" };
  }
  if (pathname.startsWith("/tree/")) return { view: "files", dir: decodeRest(pathname, "/tree/") };
  return { view: "files", dir: "" };
}

export function routeToUrl(route: Route): string {
  switch (route.view) {
    case "notebook":
      return `/notebooks/${encodeRest(route.path)}`;
    case "settings":
      return route.runtime ? `/settings?runtime=${encodeURIComponent(route.runtime)}` : "/settings";
    case "appearance":
      return "/settings/appearance";
    case "files":
      return route.dir ? `/tree/${encodeRest(route.dir)}` : "/";
  }
}

interface RouterState {
  route: Route;
  navigate: (route: Route, opts?: { replace?: boolean }) => void;
}

export const useRouter = create<RouterState>((set) => ({
  route: parseRoute(window.location.pathname, window.location.search),
  navigate: (route, opts) => {
    const url = routeToUrl(route);
    if (opts?.replace) window.history.replaceState(null, "", url);
    else if (url !== window.location.pathname + window.location.search) window.history.pushState(null, "", url);
    set({ route });
  },
}));

window.addEventListener("popstate", () => {
  useRouter.setState({ route: parseRoute(window.location.pathname, window.location.search) });
});

/** Atalhos de navegação usados pelos componentes. */
export const openHome = (opts?: { replace?: boolean }) => useRouter.getState().navigate({ view: "files", dir: "" }, opts);
export const openNotebook = (path: string, opts?: { replace?: boolean }) =>
  useRouter.getState().navigate({ view: "notebook", path }, opts);
/** Abre Runtimes; com `runtime`, a tela rola até a seção desse runtime e a destaca. */
export const openSettings = (runtime?: RuntimeKind) =>
  // Valida em runtime: o item de menu pode repassar um argumento que não é RuntimeKind.
  useRouter.getState().navigate(isRuntimeKind(runtime) ? { view: "settings", runtime } : { view: "settings" });
const FROM_APP_STATE = { notisbookFromApp: true };

export const openAppearance = () => {
  const router = useRouter.getState();
  const alreadyThere = router.route.view === "appearance";
  router.navigate({ view: "appearance" });
  // Marca a entrada criada aqui: a anterior é do app, então `history.back()` é seguro.
  if (!alreadyThere) window.history.replaceState(FROM_APP_STATE, "");
};

/** True se a entrada anterior do histórico é do app (a atual foi aberta por `openAppearance`). */
export function previousEntryIsApp(): boolean {
  const state: unknown = window.history.state;
  return typeof state === "object" && state !== null && "notisbookFromApp" in state;
}

/** Path do notebook ativo segundo a rota (ou null). */
export function activeNotebookPath(route: Route): string | null {
  return route.view === "notebook" ? route.path : null;
}
