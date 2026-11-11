/**
 * Uso de memória/CPU/disco da máquina. Polling com setTimeout encadeado (nunca
 * sobrepõe leituras), pausado com a aba oculta e retomado com leitura imediata.
 * Falhas são silenciosas: mantém os últimos valores e, após 3 seguidas, espaça as leituras.
 */
import { create } from "zustand";
import { getSystemResources, type SystemResources } from "../api/system";

const INTERVAL_MS = 5_000;
const BACKOFF_INTERVAL_MS = 30_000;
const BACKOFF_AFTER_FAILURES = 3;

interface SystemResourcesState {
  data: SystemResources | null;
  start: () => void;
  stop: () => void;
}

let running = false;
let timer: ReturnType<typeof setTimeout> | null = null;
let controller: AbortController | null = null;
let failures = 0;
let inFlight = false;

function clearTimer(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
}

function schedule(delay: number): void {
  clearTimer();
  if (!running || document.hidden) return;
  timer = setTimeout(() => void tick(), delay);
}

async function tick(): Promise<void> {
  if (!running || inFlight) return;
  inFlight = true;
  controller = new AbortController();
  try {
    const data = await getSystemResources(controller.signal);
    if (!running) return;
    failures = 0;
    useSystemResources.setState({ data });
  } catch {
    if (!running) return;
    failures += 1;
  } finally {
    inFlight = false;
    controller = null;
  }
  if (running) schedule(failures >= BACKOFF_AFTER_FAILURES ? BACKOFF_INTERVAL_MS : INTERVAL_MS);
}

function onVisibility(): void {
  if (!running) return;
  if (document.hidden) {
    clearTimer();
  } else if (!inFlight) {
    clearTimer();
    void tick();
  }
}

export const useSystemResources = create<SystemResourcesState>(() => ({
  data: null,
  start: () => {
    if (running) return;
    running = true;
    failures = 0;
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) void tick();
  },
  stop: () => {
    running = false;
    clearTimer();
    controller?.abort();
    document.removeEventListener("visibilitychange", onVisibility);
  },
}));
