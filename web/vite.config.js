import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy the API and the recording proxy to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/v1": "http://localhost:8000",
    },
  },
});
