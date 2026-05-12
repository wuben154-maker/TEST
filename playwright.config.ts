import { defineConfig } from "@playwright/test";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { readFileSync, existsSync } from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function loadEnvFileAt(filePath: string): Record<string, string> {
  if (!existsSync(filePath)) return {};
  const out: Record<string, string> = {};
  for (const line of readFileSync(filePath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let v = trimmed.slice(eq + 1).trim();
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    )
      v = v.slice(1, -1);
    out[key] = v;
  }
  return out;
}

// Later entries override earlier ones. e2e/* allows credentials only under e2e/ without touching root .env.
const fileEnv = {
  ...loadEnvFileAt(join(__dirname, ".env")),
  ...loadEnvFileAt(join(__dirname, ".env.local")),
  ...loadEnvFileAt(join(__dirname, "e2e", ".env")),
  ...loadEnvFileAt(join(__dirname, "e2e", ".env.local")),
};
// Merge into process.env so auth.setup and workers see E2E_* / LOCAL_AUTH_* (CI env still wins)
for (const [k, v] of Object.entries(fileEnv)) {
  if (process.env[k] === undefined) process.env[k] = v;
}
const env = { ...fileEnv, ...process.env };

const BASE_URL = (
  env.LOCAL_AUTH_FRONTEND_URL || "http://127.0.0.1:8080"
).replace(/\/$/, "");

export default defineConfig({
  testDir: "./e2e/tests",
  outputDir: "./e2e/test-results",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "e2e/html-report" }]],

  use: {
    baseURL: BASE_URL,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    locale: "en-US",
  },

  projects: [
    {
      name: "auth-setup",
      testDir: join(__dirname, "e2e"),
      testMatch: /auth\.setup\.ts$/,
    },
    {
      name: "chromium",
      testIgnore: /\.noauth\.spec\.ts$/,
      use: {
        browserName: "chromium",
        storageState: "e2e/.auth/state.json",
      },
      dependencies: ["auth-setup"],
    },
    {
      name: "chromium-no-auth",
      use: { browserName: "chromium" },
      testMatch: /\.noauth\.spec\.ts$/,
    },
  ],

  webServer: {
    command: "npm run dev",
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
