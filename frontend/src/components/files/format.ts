/** Formatação de metadados de arquivos (en-US). */

const relative = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });
const absolute = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" });

const STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.35],
  ["month", 12],
  ["year", Number.POSITIVE_INFINITY],
];

/** `mtime` em segundos epoch → "há 5 minutos". */
export function formatRelative(mtime: number, now = Date.now()): string {
  let value = (mtime * 1000 - now) / 1000;
  for (const [unit, size] of STEPS) {
    if (Math.abs(value) < size) return relative.format(Math.round(value), unit);
    value /= size;
  }
  return absolute.format(new Date(mtime * 1000));
}

export function formatAbsolute(mtime: number): string {
  return absolute.format(new Date(mtime * 1000));
}

export function formatSize(size: number | null): string {
  if (size === null) return "—";
  if (size < 1024) return `${size} B`;
  const units = ["KB", "MB", "GB"];
  let v = size / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}
