import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies /api to the backend on :8000.
// `VITE_MOCK=1 npm run dev` uses frontend/mocks/ instead (no backend needed).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "jsdom", globals: true },
});
