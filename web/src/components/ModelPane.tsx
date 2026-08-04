import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { monoFont } from "../theme";

const TITLE: Record<string, string> = {
  select: "choosing theorems",
  describe: "writing the description",
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
  const text = Object.entries(model);
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
      {text.length === 0 && (
        <Typography variant="caption">the model has not been asked anything yet</Typography>
      )}
      <Stack spacing={2}>
        {text.map(([key, body]) => (
          <Box key={key}>
            <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
              {TITLE[key] ?? key}
              {phase === key ? " …" : ""}
            </Typography>
            <Box sx={{ color: "#111" }}>{body}</Box>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
