import type { ReactElement } from "react";
import { FileCsvIcon, FileJsonIcon, FileTextIcon } from "../shell/icons";
import { AvroIcon, DeltaIcon, OrcIcon, ParquetIcon } from "../shell/techIcons";
import { BrandIcon } from "./BrandIcon";

/** Ícone de um arquivo pela extensão; `null` quando o formato não tem ícone próprio. */
export function fileFormatIcon(ext: string): ReactElement | null {
  switch (ext) {
    case "parquet":
      return <BrandIcon icon={ParquetIcon} />;
    case "avro":
      return <BrandIcon icon={AvroIcon} />;
    case "orc":
      return <BrandIcon icon={OrcIcon} />;
    case "csv":
    case "tsv":
    case "psv":
      return <FileCsvIcon size={14} />;
    case "json":
    case "jsonl":
    case "ndjson":
      return <FileJsonIcon size={14} />;
    case "txt":
      return <FileTextIcon size={14} />;
    case "delta":
      return <BrandIcon icon={DeltaIcon} />;
    default:
      return null;
  }
}
