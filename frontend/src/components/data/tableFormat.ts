import { DeltaIcon, HudiIcon, IcebergIcon, ParquetIcon, type TechIcon } from "../shell/techIcons";

/** Rótulo de exibição por formato de tabela (chave normalizada em minúsculas). */
const LABELS: Record<string, string> = { delta: "Delta", parquet: "Parquet", iceberg: "Iceberg", hudi: "Hudi" };
/** Ícone por formato de tabela (delta, hudi, iceberg, parquet). */
const ICONS: Record<string, TechIcon> = { delta: DeltaIcon, hudi: HudiIcon, iceberg: IcebergIcon, parquet: ParquetIcon };

/** Rótulo legível do formato; formato desconhecido é exibido como veio. */
export function tableFormatLabel(format: string): string {
  const key = format.toLowerCase();
  return Object.hasOwn(LABELS, key) ? (LABELS[key] as string) : format;
}

/** Ícone do formato, ou `null` quando desconhecido (o chamador decide o fallback). */
export function tableFormatIcon(format: string): TechIcon | null {
  const key = format.toLowerCase();
  return Object.hasOwn(ICONS, key) ? (ICONS[key] as TechIcon) : null;
}
