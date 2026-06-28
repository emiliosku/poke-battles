import { defineConfig } from "@playwright/test";

// ``PLAYWRIGHT_BASE_URL`` lets CI/local runs point at a deployed site
// instead of the dev server (default ``http://localhost:5173``). When
// pointing at a deployed site the URL must end in a trailing slash
// (or be just an origin) so ``page.goto("/")`` resolves to the app
// root rather than the host root.
const BASE_URL =
  process.env.PLAYWRIGHT_BASE_URL ||
  `http://localhost:${Number(process.env.PLAYWRIGHT_PORT || 5173)}`;

// Self-signed TLS cert on the prod host. ``PLAYWRIGHT_IGNORE_HTTPS_ERRORS=1``
// opts out of cert validation; the default keeps CI honest about real certs.
const IGNORE_HTTPS = process.env.PLAYWRIGHT_IGNORE_HTTPS_ERRORS === "1";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    ignoreHTTPSErrors: IGNORE_HTTPS,
    headless: true,
    viewport: { width: 1280, height: 900 },
    deviceScaleFactor: 1,
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    trace: "off",
    video: "off",
    screenshot: "off",
  },
});
