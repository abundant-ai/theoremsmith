import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import { api, type Run } from "../api";
import NewRunDialog from "../components/NewRunDialog";
import StatusChip from "../components/StatusChip";
import { since } from "../format";

export default function Runs() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState("");
  const [configured, setConfigured] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api.config().then((c) => {
      setModels(`create ${c.create_model} · solve ${c.solve_model}`);
      setConfigured(c.configured);
    });
  }, []);

  useEffect(() => {
    let live = true;
    const tick = () => api.runs().then((r) => live && setRuns(r.runs)).catch(() => {});
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  return (
    <Stack spacing={3}>
      {!configured && (
        <Alert severity="warning" variant="outlined" sx={{ borderRadius: 1 }}>
          THEOREMSMITH_API_KEY is not set on the server. Runs cannot start until it is.
        </Alert>
      )}

      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="caption">
          {models || " "}
        </Typography>
        <Button variant="contained" onClick={() => setOpen(true)} disabled={!configured}>
          New run
        </Button>
      </Stack>

      {runs === null ? null : runs.length === 0 ? (
        <Box sx={{ border: 1, borderColor: "divider", p: 6, textAlign: "center" }}>
          <Typography variant="body2" color="text.secondary">
            No runs yet. Point it at a Lean 4 repository and watch a proof task get built.
          </Typography>
        </Box>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Repository</TableCell>
              <TableCell>Targets</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Updated</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {runs.map((run) => (
              <TableRow
                key={run.id}
                hover
                sx={{ cursor: "pointer" }}
                onClick={() => navigate(`/runs/${run.id}`)}
              >
                <TableCell>
                  <Typography
                    component={Link}
                    to={`/runs/${run.id}`}
                    variant="body2"
                    sx={{ color: "text.primary", textDecoration: "none" }}
                  >
                    {run.repo}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {run.result?.targets?.length ? run.result.targets.join(", ") : "—"}
                  </Typography>
                </TableCell>
                <TableCell>
                  <StatusChip run={run} />
                </TableCell>
                <TableCell align="right">
                  <Typography variant="caption">{since(run.updated)}</Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <NewRunDialog
        open={open}
        onClose={() => setOpen(false)}
        onCreated={(run) => navigate(`/runs/${run.id}`)}
      />
    </Stack>
  );
}
