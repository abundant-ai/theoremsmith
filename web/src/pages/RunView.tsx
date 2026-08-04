import { Link, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { api } from "../api";
import LogPane from "../components/LogPane";
import ModelPane from "../components/ModelPane";
import Stages from "../components/Stages";
import StatusChip from "../components/StatusChip";
import { monoFont } from "../theme";
import { useRunStream } from "../useRunStream";

export default function RunView() {
  const { id = "" } = useParams();
  const { run, logs, model, phase, connected } = useRunStream(id);

  if (!run) return <Typography variant="body2">loading</Typography>;

  const result = run.result;

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "baseline" }}>
          <Typography component={Link} to="/" variant="caption" sx={{ color: "text.secondary" }}>
            runs
          </Typography>
          <Typography variant="h2">{run.repo}</Typography>
          <Typography variant="caption" sx={{ fontFamily: monoFont }}>
            {run.sha.slice(0, 10)}
          </Typography>
          <StatusChip run={run} />
        </Stack>
        {result?.slots ? (
          <Button variant="outlined" href={api.taskUrl(run.id)}>
            Download task
          </Button>
        ) : null}
      </Stack>

      <Stages stages={run.stages} />

      {run.error && (
        <Alert severity="error" variant="outlined" sx={{ borderRadius: 1, fontSize: 13 }}>
          {run.error}
        </Alert>
      )}

      {result?.targets?.length ? (
        <Box sx={{ border: 1, borderColor: "divider", p: 2 }}>
          <Typography variant="caption" sx={{ display: "block", mb: 1 }}>
            {result.slots} proof{result.slots === 1 ? "" : "s"} removed
            {result.support ? ` · ${result.support} of them supporting lemmas` : ""}
            {result.verified === true ? " · the grader gives the original proofs reward 1" : ""}
            {result.verified === false ? " · the original proofs did not earn reward 1" : ""}
          </Typography>
          <Stack spacing={1.5} sx={{ maxHeight: 300, overflow: "auto" }}>
            {result.targets.map((t) => (
              <Box key={t}>
                <Typography variant="body2" sx={{ fontFamily: monoFont }}>
                  {t}
                </Typography>
                {result.statements?.[t] && (
                  <Box
                    sx={{
                      mt: 0.5,
                      maxHeight: 96,
                      overflow: "auto",
                      fontFamily: monoFont,
                      fontSize: 11.5,
                      lineHeight: 1.5,
                      color: "text.secondary",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {result.statements[t]}
                  </Box>
                )}
              </Box>
            ))}
          </Stack>
        </Box>
      ) : null}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" sx={{ display: "block", mb: 0.75 }}>
            model
          </Typography>
          <ModelPane model={model} phase={phase} height={360} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" sx={{ display: "block", mb: 0.75 }}>
            build output {connected ? "" : "(stream closed)"}
          </Typography>
          <LogPane
            logs={logs}
            height={360}
            empty={run.status === "queued" || run.status === "running"
              ? "waiting for output"
              : "this run has finished; its output is not kept after a restart"}
          />
        </Box>
      </Stack>

      <Divider />
      <Typography variant="caption">
        The task directory holds the cut repository under <code>environment/</code>, one empty answer
        file per removed proof under <code>answers/</code>, the grader under <code>tests/</code>, and
        the original proofs under <code>solution/</code>.
      </Typography>
    </Stack>
  );
}
