import Chip from "@mui/material/Chip";

import type { Run } from "../api";

const COLOR = {
  queued: "default",
  running: "default",
  done: "success",
  failed: "error",
} as const;

export default function StatusChip({ run }: { run: Run }) {
  const label = run.status === "running" && run.stage ? run.stage : run.status;
  return (
    <Chip
      label={label}
      size="small"
      variant="outlined"
      color={COLOR[run.status]}
      sx={{ fontFamily: "inherit" }}
    />
  );
}
