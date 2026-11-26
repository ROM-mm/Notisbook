import { FileCsvIcon, FileJsonIcon } from "../shell/icons";
import { AvroIcon, DeltaIcon, HudiIcon, IcebergIcon, OrcIcon, ParquetIcon, type TechIcon } from "../shell/techIcons";

/** Rótulo de exibição por formato de tabela (chave normalizada em minúsculas). */
const LABELS: Record<string, string> = {
  delta: "Delta",
  parquet: "Parquet",
  iceberg: "Iceberg",
  hudi: "Hudi",
  csv: "CSV",
  json: "JSON",
  orc: "ORC",
  avro: "Avro",
};
/** Ícone por formato de tabela; csv/json/orc/avro seguem os mesmos desenhos de `fileFormatIcon`. */
const ICONS: Record<string, TechIcon> = {
  delta: DeltaIcon,
  hudi: HudiIcon,
  iceberg: IcebergIcon,
  parquet: ParquetIcon,
  csv: FileCsvIcon,
  json: FileJsonIcon,
  orc: OrcIcon,
  avro: AvroIcon,
};

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
