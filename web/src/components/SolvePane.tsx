import { useEffect, useRef, useState } from "react";

export default function SolvePane({ runId, height = 360 }: { runId: string; height?: number }) {
  const [lines, setLines] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLines([]);
    setDone(false);
    const source = new EventSource(`/api/runs/${runId}/solve/events`);
    source.onmessage = (e) => {
      const d = JSON.parse(e.data) as { text?: string; done?: boolean };
      if (d.done) {
        setDone(true);
        source.close();
        return;
      }
      if (d.text != null) setLines((prev) => [...prev.slice(-2000), d.text!]);
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId]);

  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div ref={box} className="mono-panel" style={{ height }}>
      {lines.length === 0 && !done && (
        <span style={{ color: "var(--gray-10)" }}>waiting for the Oddish solver…</span>
      )}
      {lines.map((line, i) => (
        <div key={i} style={{ color: "var(--gray-12)" }}>
          {line}
        </div>
      ))}
      {done && (
        <div style={{ marginTop: 10, color: "var(--gray-10)" }}>— solver finished; full run on Oddish —</div>
      )}
    </div>
  );
}
