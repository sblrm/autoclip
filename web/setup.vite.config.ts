import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
  build: {
    outDir: "dist",
    emptyOutDir: false,
    rollupOptions: { input: "ux.html" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["ux/SetupStudio.test.tsx"],
    setupFiles: "./src/test-setup.ts",
  },
});
