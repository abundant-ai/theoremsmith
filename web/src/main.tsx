import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";

import { theme } from "./theme";
import Shell from "./Shell";
import Runs from "./pages/Runs";
import RunView from "./pages/RunView";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<Runs />} />
            <Route path="/runs/:id" element={<RunView />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
