import { useSystemResources } from "../../state/systemResources";
import styles from "./AppShell.module.css";

const GIB = 1024 ** 3;
const GB = 1000 ** 3;

function pct(used: number, total: number): string {
  return total > 0 ? `${Math.round((used / total) * 100)}%` : "n/a";
}

/** Uso da máquina na topbar; escondido até a primeira leitura, e métricas `null` são omitidas. */
export function SystemResources() {
  const data = useSystemResources((s) => s.data);
  if (!data) return null;
  const { memory, cpu, disk } = data;
  const parts: string[] = [];
  const hints: string[] = [];
  if (memory) {
    parts.push(`RAM ${(memory.used / GIB).toFixed(1)}/${Math.round(memory.total / GIB)} GB`);
    hints.push(`RAM ${pct(memory.used, memory.total)}`);
  }
  if (cpu) {
    parts.push(`CPU ${((cpu.percent * cpu.cores) / 100).toFixed(1)}/${cpu.cores}`);
    hints.push(`CPU ${Math.round(cpu.percent)}%`);
  }
  if (disk) {
    parts.push(`Disk ${Math.round(disk.used / GB)}/${Math.round(disk.total / GB)} GB`);
    hints.push(`Disk ${pct(disk.used, disk.total)}`);
  }
  if (parts.length === 0) return null;
  return (
    <span className={styles.sysResources} data-testid="system-resources" title={hints.join(" · ")}>
      {parts.join(" · ")}
    </span>
  );
}
