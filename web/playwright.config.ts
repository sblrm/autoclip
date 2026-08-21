import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:8766", headless: true },
  webServer: {
    command: "..\\.venv\\Scripts\\python.exe ..\\tests\\browser_smoke_server.py",
    url: "http://127.0.0.1:8766/",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
