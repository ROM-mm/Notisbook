/**
 * Roteamento mínimo por History API (sem biblioteca). A rota define o
 * conteúdo da área principal:
 *   /                      → início (nenhum notebook ativo)
 *   /tree/<dir>            → início; a árvore de Notebooks é expandida até <dir> (abertura direta e Browse)
 *   /notebooks/<path>      → aba do notebook <path> ativa (abre a aba se preciso)
 *   /settings/appearance   → Settings › Appearance (fontes)
 *   /settings              → Settings (gestão do Spark); `/spark` é alias legado
 * Em produção o FastAPI devolve index.html para essas rotas (fallback SPA).
 */
import { create } from "zustand";

export type Route = { view: "files"; dir: string } | { view: "notebook"; path: string } | { view: "settings" } | { view: "appearance" };

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

export function parseRoute(pathname: string): Route {
  if (pathname.startsWith("/notebooks/")) return { view: "notebook", path: decodeRest(pathname, "/notebooks/") };
  if (isUnder(pathname, "/settings/appearance")) return { view: "appearance" };
  if (isUnder(pathname, "/settings") || isUnder(pathname, "/spark")) return { view: "settings" };
  if (pathname.startsWith("/tree/")) return { view: "files", dir: decodeRest(pathname, "/tree/") };
  return { view: "files", dir: "" };
}

export function routeToUrl(route: Route): string {
  switch (route.view) {
    case "notebook":
      return `/notebooks/${encodeRest(route.path)}`;
    case "settings":
      return "/settings";
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
  route: parseRoute(window.location.pathname),
  navigate: (route, opts) => {
    const url = routeToUrl(route);
    if (opts?.replace) window.history.replaceState(null, "", url);
    else if (url !== window.location.pathname) window.history.pushState(null, "", url);
    set({ route });
  },
}));

window.addEventListener("popstate", () => {
  useRouter.setState({ route: parseRoute(window.location.pathname) });
});

/** Atalhos de navegação usados pelos componentes. */
export const openHome = (opts?: { replace?: boolean }) => useRouter.getState().navigate({ view: "files", dir: "" }, opts);
export const openNotebook = (path: string, opts?: { replace?: boolean }) =>
  useRouter.getState().navigate({ view: "notebook", path }, opts);
export const openSettings = () => useRouter.getState().navigate({ view: "settings" });
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
