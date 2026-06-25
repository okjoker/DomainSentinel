import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the SPA runs on :5173 and proxies API calls to the FastAPI backend on
// :8080. In production FastAPI serves the built assets from the same origin, so
// the app always talks to relative "/api" paths.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8080",
      "/healthz": "http://localhost:8080",
    },
  },
  build: {
    outDir: "dist",
  },
});
