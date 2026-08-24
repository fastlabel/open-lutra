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
          // Streaming endpoints (SSE / MJPEG) must surface a dead backend to the
          // browser as a network error so EventSource's built-in auto-reconnect
          // kicks in: the default behavior either answers 500 (which kills an
          // EventSource permanently) or leaves the browser-side socket open
          // (which hangs it forever on a half-open stream).
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
