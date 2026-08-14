import { useEffect, useRef } from "react";

import type { Event } from "../api";

const COLOR: Record<string, string> = { error: "var(--red-11)", warn: "var(--amber-11)" };

export default function LogPane({
  logs,
  height = 320,
  empty = "waiting for output",
}: {
  logs: Event[];
  height?: number;
  empty?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom) el.scrollTop = el.scrollHeight;
  }, [logs.length]);

  return (
    <div ref={box} className="mono-panel" style={{ height }}>
      {logs.length === 0 && <div style={{ color: "var(--gray-10)" }}>{empty}</div>}
      {logs.map((e) => (
        <div key={e.seq} style={{ color: COLOR[e.level ?? ""] ?? "var(--gray-12)" }}>
          {e.text}
        </div>
      ))}
    </div>
  );
}
