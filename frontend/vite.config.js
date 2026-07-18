import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Lets the frontend call /api/... directly without hardcoding
      // localhost:5000 everywhere, and sidesteps CORS entirely in dev.
      "/api": {
        // 127.0.0.1 (not localhost): on macOS, localhost also resolves to
        // IPv6 ::1, where the AirPlay Receiver squats on :5000 and returns
        // 403. Forcing IPv4 reaches the Flask backend directly.
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
