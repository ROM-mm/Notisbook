/**
 * Resumo de erros do Spark a partir de `ename/evalue/traceback` (funções puras).
 *
 * Só afeta a exibição: o que vai para o `.ipynb` não é tocado. Formatos
 * cobertos: PySpark 3.5 (`line N pos M`, plano lógico após `;\n'`) e 4.x
 * (`SQLSTATE: XXXXX`, `== SQL (line N, position M) ==`).
 */
import { stripEscapes } from "./ansi";

const SPARK_ENAMES = new Set([
  "AnalysisException",
  "ParseException",
  "IllegalArgumentException",
  "Py4JJavaError",
  "StreamingQueryException",
  "QueryExecutionException",
  "PythonException",
  "UnknownException",
  "SparkRuntimeException",
  "SparkUpgradeException",
  "ArithmeticException",
  "NumberFormatException",
  "DateTimeException",
  "ArrayIndexOutOfBoundsException",
]);

/** Frame de traceback que passa por código do PySpark/py4j. */
const SPARK_FRAME = /^\s*File\s.*[\\/](?:pyspark|py4j)[\\/]/m;
const MAX_LINES = 3;
const MAX_CHARS = 500;

export interface RootCause {
  /** Nome simples da classe (ex.: `NumberFormatException`). */
  name: string;
  /** Nome totalmente qualificado, para `title`. */
  fqcn: string;
  message: string;
}

export interface SparkErrorSummary {
  errorClass: string | null;
  message: string;
  sqlState: string | null;
  /** Posição como veio (ex.: `line 1 pos 14`). */
  position: string | null;
  /** Só em Py4JJavaError. */
  rootCause: RootCause | null;
  /** Exceção de topo do stack Java, quando difere da causa raiz. */
  topException: RootCause | null;
}

export function isSparkError(ename: string, traceback: readonly string[], forceSql = false): boolean {
  if (forceSql) return true;
  if (SPARK_ENAMES.has(ename) || ename.startsWith("PySpark")) return true;
  return SPARK_FRAME.test(stripEscapes(traceback.join("\n")));
}

const JAVA_LINE = /^(?:Caused by: |: )?((?:[a-z_][\w$]*\.)+[A-Z][\w$]*)(?:: (.*))?$/;

function toCause(fqcn: string, message: string | undefined): RootCause {
  return { name: fqcn.slice(fqcn.lastIndexOf(".") + 1), fqcn, message: (message ?? "").trim() };
}

/** Stack Java em `Py4JJavaError`: exceção de topo, causa raiz (só via `Caused by:`) e onde começa o stack. */
function parseJava(evalue: string): { head: string; top: RootCause | null; root: RootCause | null } {
  const lines = evalue.split("\n");
  const first = lines.findIndex((l) => JAVA_LINE.test(l));
  if (first < 0) return { head: evalue, top: null, root: null };
  const found: { cause: RootCause; caused: boolean }[] = [];
  for (const line of lines.slice(first)) {
    const m = JAVA_LINE.exec(line);
    if (m?.[1] && !line.startsWith("\t")) found.push({ cause: toCause(m[1], m[2]), caused: line.startsWith("Caused by: ") });
  }
  const lastCaused = [...found].reverse().find((f) => f.caused);
  return { head: lines.slice(0, first).join("\n"), top: found[0]?.cause ?? null, root: lastCaused?.cause ?? null };
}

function limit(text: string): string {
  const lines = text.split("\n").filter((l) => l.trim() !== "");
  let out = lines.slice(0, MAX_LINES).join("\n");
  let cut = lines.length > MAX_LINES;
  if (out.length > MAX_CHARS) {
    out = out.slice(0, MAX_CHARS);
    cut = true;
  }
  return cut ? `${out.trimEnd()}…` : out;
}

export function summarizeSparkError(ename: string, evalue: string): SparkErrorSummary {
  const clean = stripEscapes(evalue);
  let rootCause: RootCause | null = null;
  let topException: RootCause | null = null;
  let text = clean;

  if (ename === "Py4JJavaError") {
    const java = parseJava(clean);
    // A classe/SQLSTATE/posição vivem na mensagem da exceção Java; o cabeçalho é só o fallback.
    text = (java.top?.message || java.head).replace(/[:\s]+$/, "");
    rootCause = java.root;
    if (java.top && java.root && java.top.fqcn !== java.root.fqcn) topException = java.top;
  }

  text = text.split("\n\nJVM stacktrace:")[0] ?? text;
  // 3.5 anexa o plano lógico depois de `;\n'`.
  const plan = text.indexOf(";\n'");
  if (plan >= 0) text = text.slice(0, plan);
  // Eco do SQL com `^^^` (ParseException).
  const echo = text.search(/\n\s*== SQL/);
  const echoBlock = echo >= 0 ? text.slice(echo) : "";
  if (echo >= 0) text = text.slice(0, echo);

  const classMatch = /^\s*\[([A-Z0-9_.]+)\]\s*/.exec(text);
  const errorClass = classMatch?.[1] ?? null;
  if (classMatch) text = text.slice(classMatch[0].length);

  const stateMatch = /[;\s]*SQLSTATE:\s*([0-9A-Z]{5})/.exec(text);
  const sqlState = stateMatch?.[1] ?? null;
  if (stateMatch) text = text.replace(stateMatch[0], "");

  const posRe = /\bline \d+,? pos(?:ition)? \d+/;
  const position = (posRe.exec(text) ?? posRe.exec(echoBlock))?.[0] ?? null;
  text = text.replace(/[;\s]*\(?\bline \d+,? pos(?:ition)? \d+\)?;?/, "");

  return { errorClass, message: limit(text.replace(/[;\s]+$/, "")), sqlState, position, rootCause, topException };
}
