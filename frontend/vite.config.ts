import type { IncomingMessage } from "node:http";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** Backend FastAPI (sempre 127.0.0.1:8765 no MVP). */
const BACKEND = "http://127.0.0.1:8765";
const DEV_PORT = 5173;

/**
 * Origens do próprio dev server. O backend só aceita WS com Origin
 * http://127.0.0.1:8765 ou http://localhost:8765, então o proxy reescreve o
 * Origin do upgrade (`rewriteWsOrigin`, Vite 8: `proxyReq.setHeader("origin", target)`
 * no evento `proxyReqWs`). Como reescrever o Origin abriria CSRF via proxy,
 * recusamos (404, sem encaminhar) qualquer upgrade cujo Origin original não seja
 * o dev server local.
 */
const DEV_ORIGINS = new Set([`http://localhost:${DEV_PORT}`, `http://127.0.0.1:${DEV_PORT}`]);

export default defineConfig({
  plugins: [react()],
  server: {
    port: DEV_PORT,
    strictPort: true,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true, // Host: 127.0.0.1:8765 (exigido pelo guard do backend)
        ws: true,
        rewriteWsOrigin: true, // Origin: http://127.0.0.1:8765 no upgrade WS
        // No upgrade WS o Vite chama `bypass(req, undefined, opts)`; `false` responde 404.
        bypass: (req: IncomingMessage, res) => {
          if (res !== undefined) return undefined; // HTTP comum: segue para o proxy
          const origin = req.headers.origin;
          return origin !== undefined && DEV_ORIGINS.has(origin) ? undefined : false;
        },
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
