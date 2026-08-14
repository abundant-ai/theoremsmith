import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Theme } from "@radix-ui/themes";
import "@radix-ui/themes/styles.css";
import "./app.css";

import Shell from "./Shell";
import Runs from "./pages/Runs";
import RunView from "./pages/RunView";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Theme
      accentColor="gray"
      grayColor="sand"
      radius="large"
      scaling="100%"
      appearance="light"
      panelBackground="translucent"
    >
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<Runs />} />
            <Route path="/runs/:id" element={<RunView />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </Theme>
  </StrictMode>,
);
