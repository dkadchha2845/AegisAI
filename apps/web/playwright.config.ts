import { defineConfig, devices } from "@playwright/test";

/**
 * The end-to-end smoke test (T-15): the real web app against the real API.
 *
 * Both servers are started here — the API in open demo mode through
 * `scripts/dev.sh`, the SPA through Vite pointed at it — or reused when they
 * are already running on a developer's machine. CI always starts its own.
 * `PW_API_PORT` / `PW_WEB_PORT` move both, and the API is told to allow the
 * web origin, so a run never collides with a dev server already on 8000/5173.
 */
const API_PORT = Number(process.env.PW_API_PORT ?? 8000);
const WEB_PORT = Number(process.env.PW_WEB_PORT ?? 5173);
const CI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: CI ? 1 : 0,
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "bash ../../scripts/dev.sh api",
      url: `http://localhost:${API_PORT}/api/health`,
      env: {
        PORT: String(API_PORT),
        AEGIS_AUTH: "0",
        AEGIS_CORS_ORIGINS: `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}`,
      },
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { VITE_API_BASE: `http://localhost:${API_PORT}` },
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
