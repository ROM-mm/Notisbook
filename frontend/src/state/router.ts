/**
 * Roteamento mínimo por History API (sem biblioteca). A rota define o
 * conteúdo da área principal:
 *   /                      → início (nenhum notebook ativo)
 *   /tree/<dir>            → início com o painel Notebooks expandido até <dir>
 *   /notebooks/<path>      → aba do notebook <path> ativa (abre a aba se preciso)
 *   /settings              → Settings (gestão do Spark); `/spark` é alias legado
 * Em produção o FastAPI devolve index.html para essas rotas (fallback SPA).
 */
import { create } from "zustand";

export type Route = { view: "files"; dir: string } | { view: "notebook"; path: string } | { view: "settings" };

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

/** Path do notebook ativo segundo a rota (ou null). */
export function activeNotebookPath(route: Route): string | null {
  return route.view === "notebook" ? route.path : null;
}
