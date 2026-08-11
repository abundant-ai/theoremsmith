import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { api, type Run, type ScanOption } from "../api";
import { monoFont } from "../theme";

const EXAMPLES = [
  { repo: "stepchowfun/proofs", note: "tiny, plain-English facts" },
  { repo: "leanprover-community/batteries", note: "lists & trees, no mathlib" },
  { repo: "leanprover/TensorLib", note: "array & dtype facts, no mathlib" },
];

type Phase = "form" | "scanning" | "pick";

export default function NewRunDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (run: Run) => void;
}) {
  const [repo, setRepo] = useState("");
  const [sha, setSha] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [options, setOptions] = useState<ScanOption[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setRepo("");
    setSha("");
    setPhase("form");
    setOptions([]);
    setPicked(new Set());
    setError("");
  }

  function close() {
    onClose();
    reset();
  }

  async function scan() {
    setPhase("scanning");
    setError("");
    try {
      const res = await api.scan(repo, sha);
      if (!res.options.length) {
        setError("nothing in this repository was worth cutting into a task");
        setPhase("form");
        return;
      }
      setOptions(res.options);
      setPicked(new Set());
      setPhase("pick");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setPhase("form");
    }
  }

  function toggle(name: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  async function create(goals: string[]) {
    setBusy(true);
    setError("");
    try {
      const run = await api.create(repo, sha, goals);
      onCreated(run);
      close();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontSize: 15, fontWeight: 500 }}>New run</DialogTitle>
      <DialogContent>
        {phase !== "pick" && (
          <Stack spacing={2.5} sx={{ pt: 1 }}>
            <TextField
              label="Lean 4 repository"
              placeholder="owner/name"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              disabled={phase === "scanning"}
              autoFocus
            />
            <Box sx={{ mt: -1.5, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {EXAMPLES.map((ex) => (
                <Chip
                  key={ex.repo}
                  label={ex.repo.split("/")[1]}
                  title={`${ex.repo} — ${ex.note}`}
                  size="small"
                  variant="outlined"
                  onClick={() => setRepo(ex.repo)}
                  disabled={phase === "scanning"}
                  sx={{ fontFamily: monoFont }}
                />
              ))}
            </Box>
            <TextField
              label="Commit (optional)"
              placeholder="defaults to the default branch"
              value={sha}
              onChange={(e) => setSha(e.target.value)}
              disabled={phase === "scanning"}
            />
            {phase === "scanning" && (
              <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                <CircularProgress size={14} thickness={6} sx={{ color: "text.primary" }} />
                <Typography variant="caption">reading {repo} and choosing theorems…</Typography>
              </Stack>
            )}
            {error && (
              <Typography variant="caption" color="error">
                {error}
              </Typography>
            )}
          </Stack>
        )}

        {phase === "pick" && (
          <Stack spacing={0.5} sx={{ pt: 1 }}>
            <Typography variant="caption" sx={{ mb: 1 }}>
              Theorems in {repo}. Pick the ones to build a task from — their proofs and the helper
              lemmas only they use get cut.
            </Typography>
            <Box sx={{ maxHeight: 380, overflowY: "auto", mx: -1 }}>
              {options.map((o) => (
                <Box
                  key={o.name}
                  onClick={() => toggle(o.name)}
                  sx={{
                    display: "flex",
                    gap: 1,
                    px: 1,
                    py: 1,
                    cursor: "pointer",
                    borderBottom: 1,
                    borderColor: "divider",
                    "&:hover": { bgcolor: "#fafafa" },
                  }}
                >
                  <Checkbox
                    checked={picked.has(o.name)}
                    size="small"
                    sx={{ p: 0, mt: 0.25 }}
                    disableRipple
                  />
                  <Box sx={{ minWidth: 0 }}>
                    <Typography sx={{ fontFamily: monoFont, fontSize: 13 }}>{o.name}</Typography>
                    <Typography
                      variant="caption"
                      sx={{ fontStyle: "italic", color: "text.secondary", display: "block" }}
                    >
                      {o.gloss}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Box>
            {error && (
              <Typography variant="caption" color="error" sx={{ pt: 1 }}>
                {error}
              </Typography>
            )}
          </Stack>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        {phase === "pick" ? (
          <>
            <Button onClick={() => setPhase("form")} color="inherit" disabled={busy}>
              Back
            </Button>
            <Button
              variant="contained"
              onClick={() => create([...picked])}
              disabled={busy || picked.size === 0}
            >
              {busy ? "Starting" : `Build task (${picked.size})`}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={close} color="inherit">
              Cancel
            </Button>
            <Button
              variant="contained"
              onClick={scan}
              disabled={phase === "scanning" || repo.trim().length < 3}
            >
              {phase === "scanning" ? "Scanning" : "Scan theorems"}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
