import { useEffect, useRef, useState } from "react";
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

import { api, type Example, type Run, type ScanOption } from "../api";
import { monoFont } from "../theme";

type Phase = "form" | "scanning" | "pick";

export default function NewRunDialog({
  open,
  onClose,
  onCreated,
  examples = [],
  initialRepo = "",
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (run: Run) => void;
  examples?: Example[];
  initialRepo?: string;
}) {
  const [repo, setRepo] = useState(initialRepo);
  const [sha, setSha] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [options, setOptions] = useState<ScanOption[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [scanLog, setScanLog] = useState("");
  const stream = useRef<EventSource | null>(null);
  const logBox = useRef<HTMLDivElement>(null);

  const stopStream = () => {
    stream.current?.close();
    stream.current = null;
  };

  useEffect(() => {
    const el = logBox.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scanLog]);

  useEffect(() => {
    if (open) {
      setRepo(initialRepo);
      setPhase("form");
    }
  }, [open, initialRepo]);

  useEffect(() => stopStream, []);

  function reset() {
    stopStream();
    setRepo("");
    setSha("");
    setPhase("form");
    setOptions([]);
    setPicked(new Set());
    setError("");
    setScanLog("");
  }

  function close() {
    onClose();
    reset();
  }

  function scan() {
    setPhase("scanning");
    setError("");
    setScanLog("");
    stopStream();
    const source = new EventSource(api.scanStreamUrl(repo, sha));
    stream.current = source;
    source.onmessage = (e) => {
      const d = JSON.parse(e.data) as { text?: string; options?: ScanOption[]; error?: string };
      if (d.error) {
        stopStream();
        setError(d.error);
        setPhase("form");
        return;
      }
      if (d.text != null) {
        setScanLog((prev) => (prev + d.text).slice(-4000));
        return;
      }
      if (d.options != null) {
        stopStream();
        if (!d.options.length) {
          setError("nothing in this repository was worth cutting into a task");
          setPhase("form");
          return;
        }
        setOptions(d.options);
        setPicked(new Set());
        setPhase("pick");
      }
    };
    source.onerror = () => {
      stopStream();
      setPhase((p) => {
        if (p === "scanning") {
          setError("the scan connection dropped");
          return "form";
        }
        return p;
      });
    };
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
            {examples.length > 0 && (
              <Box sx={{ mt: -1.5, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                {examples.map((ex) => (
                  <Chip
                    key={ex.repo}
                    label={ex.repo.split("/")[1]}
                    title={ex.note ? `${ex.repo} — ${ex.note}` : ex.repo}
                    size="small"
                    variant="outlined"
                    onClick={() => setRepo(ex.repo)}
                    disabled={phase === "scanning"}
                    sx={{ fontFamily: monoFont }}
                  />
                ))}
              </Box>
            )}
            <TextField
              label="Commit (optional)"
              placeholder="defaults to the default branch"
              value={sha}
              onChange={(e) => setSha(e.target.value)}
              disabled={phase === "scanning"}
            />
            <Typography variant="caption" color="text.secondary">
              Scanning clones the repository and reads every theorem in it. For a repository that
              hasn't been scanned before this can take many minutes. The examples above are
              pre-scanned and open instantly.
            </Typography>
            {phase === "scanning" && (
              <Stack spacing={1}>
                <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                  <CircularProgress size={14} thickness={6} sx={{ color: "text.primary" }} />
                  <Typography variant="caption">
                    reading {repo} and choosing theorems — this can take many minutes…
                  </Typography>
                </Stack>
                {scanLog && (
                  <Box
                    ref={logBox}
                    sx={{
                      maxHeight: 150,
                      overflowY: "auto",
                      border: 1,
                      borderColor: "divider",
                      p: 1,
                      fontFamily: monoFont,
                      fontSize: 11,
                      lineHeight: 1.6,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      color: "text.secondary",
                    }}
                  >
                    {scanLog}
                  </Box>
                )}
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
