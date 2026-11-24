/** Ordem fixa dos formatos de tabela conhecidos; desconhecidos vão para o fim, na ordem recebida. */
const KNOWN_FORMATS = ["delta", "iceberg", "hudi"];

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

/** `true` quando o runtime tem ao menos um formato de tabela. */
export const hasFormats = (formats: string[] | null | undefined): formats is string[] =>
  !!formats && formats.some((f) => f.trim() !== "");

/**
 * Texto do selo de suporte a formatos de tabela.
 * `["delta","iceberg","hudi"]` → `Support: Delta, Iceberg & Hudi`; `null`/vazio → `No table format support`.
 */
export function supportLabel(formats: string[] | null | undefined): string {
  if (!hasFormats(formats)) return "No table format support";
  const names = [...new Set(formats.map((f) => f.trim().toLowerCase()).filter(Boolean))];
  const known = KNOWN_FORMATS.filter((f) => names.includes(f));
  const unknown = names.filter((f) => !KNOWN_FORMATS.includes(f));
  const list = [...known, ...unknown].map(capitalize);
  const last = list.pop() ?? "";
  const text = list.length ? `${list.join(", ")} & ${last}` : last;
  return `Support: ${text}`;
}
