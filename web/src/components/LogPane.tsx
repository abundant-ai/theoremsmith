import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";

import type { Event } from "../api";
import { monoFont } from "../theme";

const COLOR: Record<string, string> = { error: "#b3261e", warn: "#8a6100" };

export default function LogPane({ logs, height = 320 }: { logs: Event[]; height?: number }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [logs.length]);

  return (
    <Box
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
      {logs.length === 0 && <Box sx={{ color: "text.secondary" }}>waiting for output</Box>}
      {logs.map((e) => (
        <Box key={e.seq} sx={{ color: COLOR[e.level ?? ""] ?? "#333" }}>
          {e.text}
        </Box>
      ))}
      <div ref={end} />
    </Box>
  );
}
