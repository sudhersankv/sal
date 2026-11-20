import { resolve } from "node:path";
import { defineConfig } from "vite";

const api = "http://localhost:8100";
export default defineConfig({
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: {
      "/api": api, "/events": api, "/stream": api, "/state": api, "/replay": api, "/mode": api, "/sim": api, "/healthz": api,
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: { input: { main: resolve(__dirname, "index.html"), demo: resolve(__dirname, "demo.html") } },
  },
});
