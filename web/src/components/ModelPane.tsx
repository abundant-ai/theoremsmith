import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { monoFont } from "../theme";

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
    <Box
      ref={box}
      sx={{
        height,
        overflowY: "auto",
        border: 1,
        borderColor: "divider",
        p: 1.5,
        fontFamily: monoFont,
        fontSize: 12.5,
        lineHeight: 1.7,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {parts.length === 0 && (
        <Typography variant="caption">the builder model has not started yet</Typography>
      )}
      {parts.map(([key, body], i) => (
        <Box key={key}>
          <Typography
            variant="caption"
            sx={{ display: "block", mt: i > 0 ? 1.5 : 0, mb: 0.5, color: "text.secondary" }}
          >
            — {LABEL[key] ?? key}
            {phase === key ? " …" : ""} —
          </Typography>
          <Box sx={{ color: "#111" }}>{body}</Box>
        </Box>
      ))}
    </Box>
  );
}
