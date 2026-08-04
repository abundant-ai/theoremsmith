import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { STAGES, type StageState } from "../api";

const LABEL: Record<string, string> = {
  clone: "Clone",
  build: "Build",
  probe: "Probe",
  select: "Choose theorems",
  cut: "Cut proofs",
  emit: "Write task",
  verify: "Verify",
};

function Mark({ state }: { state: StageState }) {
  if (state === "running") return <CircularProgress size={11} thickness={6} sx={{ color: "text.primary" }} />;
  const color = state === "done" ? "success.main" : state === "failed" ? "error.main" : "divider";
  return <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color }} />;
}

export default function Stages({ stages }: { stages: Record<string, StageState> }) {
  return (
    <Stack
      direction="row"
      spacing={0}
      sx={{ border: 1, borderColor: "divider" }}
    >
      {STAGES.map((name, i) => (
        <Stack
          key={name}
          direction="row"
          spacing={1}
          sx={{
            flex: 1,
            alignItems: "center",
            px: 1.5,
            py: 1.25,
            borderLeft: i === 0 ? 0 : 1,
            borderColor: "divider",
            opacity: stages[name] === "pending" ? 0.45 : 1,
          }}
        >
          <Mark state={stages[name] ?? "pending"} />
          <Typography variant="caption" noWrap sx={{ color: "text.primary" }}>
            {LABEL[name]}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}
