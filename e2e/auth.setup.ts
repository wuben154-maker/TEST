/**
 * Playwright global setup: authenticate via Python API and persist storageState.
 *
 * Reads E2E_EMAIL / E2E_PASSWORD from env: e2e/.env.local, e2e/.env, then repo root .env
 * (same keys as npm run auth:bootstrap). See e2e/.env.example.
 * Saves localStorage auth_token + auth_user into e2e/.auth/state.json so that
 * test projects with `storageState` pick up the logged-in session automatically.
 */
import { test as setup, expect } from "@playwright/test";

const API_BASE = (
  process.env.E2E_API_BASE || "http://127.0.0.1:8000"
).replace(/\/$/, "");

setup("authenticate and save state", async ({ page }) => {
  const email = process.env.E2E_EMAIL || process.env.LOCAL_AUTH_EMAIL;
  const password = process.env.E2E_PASSWORD || process.env.LOCAL_AUTH_PASSWORD;

  if (!email || !password) {
    throw new Error(
      "E2E_EMAIL + E2E_PASSWORD (or LOCAL_AUTH_*): set in e2e/.env.local, e2e/.env, root .env, or CI env",
    );
  }

  const res = await page.request.post(`${API_BASE}/auth/login`, {
    data: { email, password },
  });
  expect(res.ok()).toBeTruthy();

  const body = await res.json();
  const token: string = body.access_token;
  const user = body.user;

  await page.goto("/");

  await page.evaluate(
    ({ token, user }) => {
      localStorage.setItem("auth_token", token);
      localStorage.setItem("auth_user", JSON.stringify(user));
    },
    { token, user },
  );

  // Avoid "networkidle": SPAs often keep long-lived connections (SSE/HMR/polling).
  await page.reload({ waitUntil: "load" });

  await page.context().storageState({ path: "e2e/.auth/state.json" });
});
