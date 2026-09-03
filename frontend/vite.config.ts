import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), TanStackRouterVite(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_URL || "http://localhost:8000",
        changeOrigin: true,
        configure: (proxy) => {
          // All /api requests: surface a dead backend as a network error, not a
          // 500/502 or a hanging half-open socket. EventSource reconnects only
          // after a network error and dies permanently on a non-200 response.
          proxy.on("error", (_err, _req, res) => {
            res.destroy();
          });
          proxy.on("proxyRes", (proxyRes, _req, res) => {
            proxyRes.on("close", () => res.destroy());
          });
        },
      },
      "/health": {
        target: process.env.API_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
