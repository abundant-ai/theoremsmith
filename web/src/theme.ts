import { createTheme } from "@mui/material/styles";

const mono = '"SFMono-Regular", "JetBrains Mono", Menlo, Consolas, monospace';

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#111111" },
    background: { default: "#ffffff", paper: "#ffffff" },
    text: { primary: "#111111", secondary: "#6b6b6b" },
    divider: "#e4e4e4",
    success: { main: "#137333" },
    error: { main: "#b3261e" },
    warning: { main: "#8a6100" },
  },
  shape: { borderRadius: 2 },
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
    h1: { fontSize: 20, fontWeight: 500, letterSpacing: "-0.01em" },
    h2: { fontSize: 15, fontWeight: 500 },
    body2: { fontSize: 13, lineHeight: 1.6 },
    caption: { fontSize: 12, color: "#6b6b6b" },
    button: { textTransform: "none", fontWeight: 400, fontSize: 13 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { WebkitFontSmoothing: "antialiased" },
        "code, pre": { fontFamily: mono },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true, size: "small" },
      styleOverrides: { root: { paddingInline: 12, minHeight: 30 } },
    },
    MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { root: { backgroundImage: "none" } } },
    MuiTextField: { defaultProps: { size: "small", fullWidth: true } },
    MuiChip: { styleOverrides: { root: { height: 20, fontSize: 11, borderRadius: 2 } } },
    MuiDialog: { styleOverrides: { paper: { border: "1px solid #e4e4e4", borderRadius: 3 } } },
    MuiTableCell: {
      styleOverrides: {
        root: { fontSize: 13, paddingBlock: 10, borderColor: "#eeeeee" },
        head: { color: "#6b6b6b", fontWeight: 400, fontSize: 12 },
      },
    },
  },
});

export const monoFont = mono;
