/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Built into ../static/app and served by Flask at /app/ (same origin, so the session
// cookie and CSRF token work without CORS). `npm run dev` proxies the API to Flask.
export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  build: { outDir: "../static/app", emptyOutDir: true, sourcemap: false },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:5055",
      "/media": "http://localhost:5055",
      "/login": "http://localhost:5055",
      "/logout": "http://localhost:5055",
      "/static": "http://localhost:5055",
    },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"], css: false },
});
