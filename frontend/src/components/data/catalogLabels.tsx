/**
 * Rótulos e ícones de exibição dos catálogos, compartilhados pela árvore do Catalog e pelo painel
 * Catalog info. Só exibição: o nome real (`spark_catalog`) segue em chaves, API e requisições.
 */
import { HudiIcon, IcebergIcon, SparkIcon, type TechIcon } from "../shell/techIcons";

/** Nome real do catálogo de sessão do Spark (usado em chaves, API e requisições). */
export const SPARK_CATALOG = "spark_catalog";

/** Nó só de exibição das tabelas Hudi: os schemas são do `spark_catalog`. */
export const HUDI_CATALOG = "hudi";

const CATALOG_LABELS: Record<string, string> = { [SPARK_CATALOG]: "spark" };
const CATALOG_ICONS: Record<string, TechIcon> = { [SPARK_CATALOG]: SparkIcon, iceberg: IcebergIcon, [HUDI_CATALOG]: HudiIcon };

/** Rótulo exibido do catálogo (`spark_catalog` → "spark"); os demais aparecem pelo nome real. */
export function catalogLabel(name: string): string {
  return Object.hasOwn(CATALOG_LABELS, name) ? (CATALOG_LABELS[name] as string) : name;
}

/** Ícone de tecnologia do catálogo, ou `undefined` quando não há um (cada chamador escolhe o fallback). */
export function catalogIcon(name: string): TechIcon | undefined {
  return Object.hasOwn(CATALOG_ICONS, name) ? CATALOG_ICONS[name] : undefined;
}
