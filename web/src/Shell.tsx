import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Container maxWidth="lg" sx={{ py: 1.5, display: "flex", alignItems: "baseline", gap: 1.5 }}>
          <Typography
            component={Link}
            to="/"
            variant="h1"
            sx={{ color: "text.primary", textDecoration: "none" }}
          >
            theoremsmith
          </Typography>
          <Typography variant="caption">
            turns a Lean repository into a proof task
          </Typography>
        </Container>
      </Box>
      <Container maxWidth="lg" sx={{ flex: 1, py: 4 }}>
        {children}
      </Container>
    </Box>
  );
}
