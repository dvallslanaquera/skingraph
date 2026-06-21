import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
// Multi-page build: the landing is the root ("/") entry; the React app is
// served from "/app". Paths are relative to the project root (this dir).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    rollupOptions: {
      input: {
        main: "index.html", // landing → dist/index.html → /
        app: "app/index.html", // React app → dist/app/index.html → /app
      },
    },
  },
});
