import { test, expect } from "@playwright/test";

test.describe("Health — no auth required", () => {
  test("Python API /health returns ok", async ({ request }) => {
    const apiBase = (
      process.env.E2E_API_BASE || "http://127.0.0.1:8000"
    ).replace(/\/$/, "");

    const res = await request.get(`${apiBase}/health`);
    expect(res.ok()).toBeTruthy();

    const body = await res.json();
    expect(body).toHaveProperty("status");
  });
});
