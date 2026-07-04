import pkg from "./package.json";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Single source of truth for the displayed app version: read it from
// package.json here and bake it into the bundle as __APP_VERSION__, so a
// `package.json` version bump is all that's needed to update the footer.
const APP_VERSION: string = pkg.version;

// https://vite.dev/config/
// Multi-page build: the landing is the root ("/") entry; the React app is
// served from "/app". Paths are relative to the project root (this dir).
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
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
