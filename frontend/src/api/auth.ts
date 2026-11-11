import { ApiError, request, setAuthToken } from "./http";

export type AuthResult = "ok" | "unauthorized";

/**
 * Se a página veio com `?token=`, a primeira chamada (`/api/health?token=`)
 * faz o backend setar o cookie `notisbook_token`; só depois removemos o token
 * da URL com `history.replaceState`. O token também fica em memória para o
 * header Bearer durante esta aba (nunca em storage).
 */
export async function bootstrapAuth(): Promise<AuthResult> {
  const url = new URL(window.location.href);
  const token = url.searchParams.get("token");
  try {
    await request<{ status: string }>("/api/health", { query: { token: token ?? undefined } });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return "unauthorized";
    throw err;
  }
  if (token) {
    setAuthToken(token);
    url.searchParams.delete("token");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }
  return "ok";
}
