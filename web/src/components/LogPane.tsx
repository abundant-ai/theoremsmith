import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";

import type { Event } from "../api";
import { monoFont } from "../theme";

const COLOR: Record<string, string> = { error: "#b3261e", warn: "#8a6100" };

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
    <Box
      ref={box}
      sx={{
        height,
        overflowY: "auto",
        border: 1,
        borderColor: "divider",
        bgcolor: "#fafafa",
        p: 1.5,
        fontFamily: monoFont,
        fontSize: 12,
        lineHeight: 1.65,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {logs.length === 0 && <Box sx={{ color: "text.secondary" }}>{empty}</Box>}
      {logs.map((e) => (
        <Box key={e.seq} sx={{ color: COLOR[e.level ?? ""] ?? "#333" }}>
          {e.text}
        </Box>
      ))}
    </Box>
  );
}
