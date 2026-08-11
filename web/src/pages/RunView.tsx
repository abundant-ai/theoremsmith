import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { api, type Config, type OddishRun, type StageState } from "../api";
import LogPane from "../components/LogPane";
import ModelPane from "../components/ModelPane";
import SolvePane from "../components/SolvePane";
import Stages from "../components/Stages";
import StatusChip from "../components/StatusChip";
import { monoFont } from "../theme";
import { useRunStream } from "../useRunStream";

export default function RunView() {
  const { id = "" } = useParams();
  const { run, logs, model, phase, connected } = useRunStream(id);
  const [cfg, setCfg] = useState<Config | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitted, setSubmitted] = useState<OddishRun | undefined>();

  useEffect(() => {
    api.config().then(setCfg).catch(() => {});
  }, []);

  if (!run) return <Typography variant="body2">loading</Typography>;

  const result = run.result;
  const oddish = submitted ?? result?.oddish;
  const canSubmit = run.status === "done" && result?.verified === true;
  const minutes = 30;
  const oddishState: StageState = oddish
    ? "done"
    : busy
      ? "running"
      : submitError
        ? "failed"
        : "pending";

  async function submit() {
    setBusy(true);
    setSubmitError("");
    try {
      setSubmitted(await api.submit(id));
      setConfirm(false);
    } catch (e) {
      setSubmitError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

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
        <Stack direction="row" spacing={1}>
          {run.status === "done" ? (
            <Button variant="outlined" href={api.taskUrl(run.id)}>
              Download task
            </Button>
          ) : null}
          {canSubmit && !oddish ? (
            <Tooltip
              title={cfg && !cfg.oddish_available ? "the oddish CLI is not available on this server" : ""}
            >
              <span>
                <Button
                  variant="contained"
                  onClick={() => setConfirm(true)}
                  disabled={!!cfg && !cfg.oddish_available}
                >
                  Run on Oddish
                </Button>
              </span>
            </Tooltip>
          ) : null}
          {oddish ? (
            <Button variant="contained" href={oddish.public_url} target="_blank" rel="noreferrer">
              Open on Oddish ↗
            </Button>
          ) : null}
        </Stack>
      </Stack>

      <Stages stages={run.stages} oddish={run.status === "done" ? oddishState : undefined} />

      {oddish && (
        <Alert severity="success" variant="outlined" sx={{ borderRadius: 1, fontSize: 13 }}>
          Sent to Oddish — {oddish.agent ?? cfg?.oddish_agent} / {oddish.model ?? cfg?.oddish_model} is
          solving it now, {minutes}-minute limit. Public link:{" "}
          <Typography
            component="a"
            href={oddish.public_url}
            target="_blank"
            rel="noreferrer"
            sx={{ fontFamily: monoFont, wordBreak: "break-all" }}
          >
            {oddish.public_url}
          </Typography>
        </Alert>
      )}

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
            {oddish
              ? `Oddish solver · ${oddish.agent ?? cfg?.oddish_agent} / ${oddish.model ?? cfg?.oddish_model}`
              : "model"}
          </Typography>
          {oddish ? (
            <SolvePane runId={id} height={360} />
          ) : (
            <ModelPane model={model} phase={phase} height={360} />
          )}
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

      <Dialog open={confirm} onClose={() => (busy ? null : setConfirm(false))} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontSize: 15, fontWeight: 500 }}>Run this task on Oddish?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            Oddish packages this task and runs it with{" "}
            <b>{cfg?.oddish_agent ?? "claude-code"}</b> on <b>{cfg?.oddish_model ?? "glm-5.2"}</b>, with
            a {minutes}-minute limit. It uses your Oddish account and returns a public link where you
            can watch the attempt live.
          </Typography>
          {submitError && (
            <Typography variant="caption" color="error" sx={{ display: "block", mt: 2 }}>
              {submitError}
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setConfirm(false)} color="inherit" disabled={busy}>
            Cancel
          </Button>
          <Button variant="contained" onClick={submit} disabled={busy}>
            {busy ? "Submitting" : "Run on Oddish"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
