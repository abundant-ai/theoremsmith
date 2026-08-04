import { useEffect, useRef, useState } from "react";

import { api, type Event, type Run } from "./api";

export type Stream = {
  run: Run | null;
  logs: Event[];
  model: Record<string, string>;
  phase: string | null;
  connected: boolean;
};

const MAX_LOGS = 1500;

export function useRunStream(id: string): Stream {
  const [run, setRun] = useState<Run | null>(null);
  const [logs, setLogs] = useState<Event[]>([]);
  const [model, setModel] = useState<Record<string, string>>({});
  const [phase, setPhase] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    let live = true;
    const refresh = () => api.run(id).then((r) => live && setRun(r)).catch(() => {});
    refresh();

    const source = new EventSource(`/api/runs/${id}/events?after=0`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (raw) => {
      const event = JSON.parse(raw.data) as Event;
      if (event.seq <= seq.current) return;
      seq.current = event.seq;
      if (event.kind === "log") {
        setLogs((prev) => [...prev.slice(-MAX_LOGS), event]);
      } else if (event.kind === "delta") {
        setModel((prev) => ({
          ...prev,
          [event.phase!]: (prev[event.phase!] ?? "") + (event.text ?? ""),
        }));
      } else if (event.kind === "model") {
        setPhase(event.state === "start" ? event.phase! : null);
      } else if (event.kind === "stage" || event.kind === "status") {
        refresh();
      } else if (event.kind === "end") {
        refresh();
        source.close();
        setConnected(false);
      }
    };
    return () => {
      live = false;
      source.close();
    };
  }, [id]);

  return { run, logs, model, phase, connected };
}
