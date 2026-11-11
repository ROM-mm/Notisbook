import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { initTheme } from "./state/theme";
// Fontes empacotadas no bundle (subconjunto latin; inclui acentos pt-BR): a CSP não permite CDN.
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-400-italic.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/fira-code/latin-500.css";
import "@fontsource/fira-code/latin-ext-500.css";
import "@fontsource/fira-code/latin-700.css";
import "@fontsource/fira-code/latin-ext-700.css";
import "@fontsource/space-grotesk/latin-500.css";
import "@fontsource/space-grotesk/latin-700.css";
import "@fontsource/public-sans/latin-400.css";
import "@fontsource/public-sans/latin-500.css";
import "@fontsource/public-sans/latin-600.css";
import "@fontsource/public-sans/latin-700.css";
import "@fontsource/archivo-black/latin-400.css";
import "@fontsource/pacifico/latin-400.css";
import "./styles/tokens.css";
import "./styles/global.css";

initTheme();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
