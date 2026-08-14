import { Badge } from "@radix-ui/themes";

import type { Run } from "../api";

const COLOR = {
  queued: "gray",
  running: "blue",
  done: "green",
  failed: "red",
} as const;

export default function StatusChip({ run }: { run: Run }) {
  const label = run.status === "running" && run.stage ? run.stage : run.status;
  return (
    <Badge color={COLOR[run.status]} variant="soft" radius="full">
      {label}
    </Badge>
  );
}
