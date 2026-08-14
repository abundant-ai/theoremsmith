import { useEffect, useRef, useState } from "react";

import { api, type Event, type Run } from "./api";

export type Stream = {
  run: Run | null;
  logs: Event[];
  connected: boolean;
};

const MAX_LOGS = 1500;

export function useRunStream(id: string): Stream {
  const [run, setRun] = useState<Run | null>(null);
  const [logs, setLogs] = useState<Event[]>([]);
  const [connected, setConnected] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    let live = true;
    const refresh = () => api.run(id).then((r) => live && setRun(r)).catch(() => {});
    refresh();
    // The build event stream ends at completion, so poll to pick up later state
    // changes — notably the Oddish link (or error) landing from a background submit.
    const poll = setInterval(refresh, 3000);

    const source = new EventSource(`/api/runs/${id}/events?after=0`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (raw) => {
      const event = JSON.parse(raw.data) as Event;
      if (event.seq <= seq.current) return;
      seq.current = event.seq;
      if (event.kind === "log") {
        setLogs((prev) => [...prev.slice(-MAX_LOGS), event]);
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
      clearInterval(poll);
      source.close();
    };
  }, [id]);

  return { run, logs, connected };
}
