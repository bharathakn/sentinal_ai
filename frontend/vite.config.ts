/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is always called at relative /api/... URLs so the session cookie is
// first-party: the dev server proxies to the local FastAPI app, and Vercel
// rewrites /api/* to Render in production (vercel.json).
const API = process.env.SENTINEL_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": API, "/health": API },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
