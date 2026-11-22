import { isValidFontName } from "../state/appearance";
import { request } from "./http";

interface SystemFontsResponse {
  status: "ok" | "unsupported" | "unavailable";
  families: unknown;
}

/** Fontes do sistema listadas pelo backend; qualquer falha ou status diferente de `ok` vira lista vazia. */
export async function fetchSystemFonts(refresh = false, signal?: AbortSignal): Promise<string[]> {
  try {
    const data = await request<SystemFontsResponse>("/api/appearance/system-fonts", {
      query: refresh ? { refresh: "true" } : undefined,
      signal,
    });
    if (data?.status !== "ok" || !Array.isArray(data.families)) return [];
    return data.families.filter((name): name is string => typeof name === "string" && isValidFontName(name));
  } catch {
    return [];
  }
}
