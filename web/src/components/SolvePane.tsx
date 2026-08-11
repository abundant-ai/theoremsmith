import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { monoFont } from "../theme";

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
      {lines.length === 0 && !done && (
        <Typography variant="caption">waiting for the Oddish solver…</Typography>
      )}
      {lines.map((line, i) => (
        <Box key={i} sx={{ color: "#111" }}>
          {line}
        </Box>
      ))}
      {done && (
        <Typography variant="caption" sx={{ display: "block", mt: 1 }}>
          — solver finished; full run on Oddish —
        </Typography>
      )}
    </Box>
  );
}
