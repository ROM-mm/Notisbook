import { request } from "./http";
import type { Sample } from "./types";

/** Exemplos presentes na raiz atual, em ordem alfabética (pode ser `[]`). */
export function listSamples(signal?: AbortSignal): Promise<Sample[]> {
  return request<Sample[]>("/api/samples", { signal });
}
