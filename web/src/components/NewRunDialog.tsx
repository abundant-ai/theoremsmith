import { useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { api, type Run } from "../api";

const EXAMPLES = ["leanprover-community/batteries"];

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
  const [goals, setGoals] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const run = await api.create(
        repo,
        sha,
        goals.split(/[\s,]+/).filter(Boolean),
      );
      onClose();
      onCreated(run);
      setRepo("");
      setSha("");
      setGoals("");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontSize: 15, fontWeight: 500 }}>New run</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          <TextField
            label="Lean 4 repository"
            placeholder="owner/name"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            helperText={`for example ${EXAMPLES[0]}`}
            autoFocus
          />
          <TextField
            label="Commit (optional)"
            placeholder="defaults to the default branch"
            value={sha}
            onChange={(e) => setSha(e.target.value)}
          />
          <TextField
            label="Theorems (optional)"
            placeholder="Namespace.theorem_name"
            value={goals}
            onChange={(e) => setGoals(e.target.value)}
            helperText="leave empty and the model picks them"
          />
          {error && (
            <Typography variant="caption" color="error">
              {error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button variant="contained" onClick={submit} disabled={busy || repo.trim().length < 3}>
          {busy ? "Starting" : "Start"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
