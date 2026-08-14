import { useEffect, useRef } from "react";

// The builder model's trajectory, in the order it happens.
const ORDER = ["select", "describe"];
const LABEL: Record<string, string> = {
  select: "choosing the theorems",
  describe: "writing the task",
};

export default function ModelPane({
  model,
  phase,
  height = 320,
}: {
  model: Record<string, string>;
  phase: string | null;
  height?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const parts = Object.entries(model).sort(
    (a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]),
  );
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom) el.scrollTop = el.scrollHeight;
  }, [JSON.stringify(model).length]);

  return (
    <div ref={box} className="mono-panel" style={{ height }}>
      {parts.length === 0 && (
        <span style={{ color: "var(--gray-10)" }}>the builder model has not started yet</span>
      )}
      {parts.map(([key, body], i) => (
        <div key={key}>
          <div style={{ marginTop: i > 0 ? 14 : 0, marginBottom: 4, color: "var(--gray-10)" }}>
            — {LABEL[key] ?? key}
            {phase === key ? " …" : ""} —
          </div>
          <div style={{ color: "var(--gray-12)" }}>{body}</div>
        </div>
      ))}
    </div>
  );
}
