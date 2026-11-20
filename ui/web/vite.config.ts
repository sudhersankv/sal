import { defineConfig } from "vite";

const api = "http://localhost:8100";
export default defineConfig({
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: {
      "/events": api, "/stream": api, "/state": api, "/replay": api, "/mode": api, "/sim": api, "/healthz": api,
    },
  },
  build: { chunkSizeWarningLimit: 1200 },
});
