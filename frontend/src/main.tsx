import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { initTheme } from "./state/theme";
// Fontes empacotadas no bundle (subconjunto latin; inclui acentos pt-BR): a CSP não permite CDN.
import "@fontsource/roboto/latin-400.css";
import "@fontsource/roboto/latin-ext-400.css";
import "@fontsource/roboto/latin-500.css";
import "@fontsource/roboto/latin-ext-500.css";
import "@fontsource/roboto/latin-600.css";
import "@fontsource/roboto/latin-ext-600.css";
import "@fontsource/roboto/latin-700.css";
import "@fontsource/roboto/latin-ext-700.css";
import "@fontsource/roboto/latin-400-italic.css";
import "@fontsource/roboto/latin-ext-400-italic.css";
import "./styles/fonts.css";
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
