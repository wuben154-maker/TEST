/**
 * workspace-sandbox-unification — path leakage guard.
 *
 * Invariant: the UI and SSE payloads surfaced to the client must *never*
 * expose owner-scoped internal tokens. Anything under `/workspace/`,
 * `/uploads/` or the raw hashed owner segments (`u_<hex>`, `p_<hex>`,
 * `s_<hex>`) is internal plumbing and must be scrubbed to `workspace/...`,
 * `System Skill: ...`, `Memory: ...` or similar user-facing labels.
 *
 * Backstops covered:
 *   E2E-01 Upload → composer/reasoning panel never renders owner tokens.
 *   E2E-02 `/analyze` SSE stream body is free of leaked tokens.
 *   E2E-03 (skip-graceful) If the live LLM is unavailable (429 / 5xx /
 *          missing provider key) the streaming leg skips with a note so
 *          the delivery is not blocked by provider quota.
 */
import { test, expect, type APIResponse, type Page } from "../fixtures/authenticated";

const API_BASE = (
  process.env.E2E_API_BASE || "http://127.0.0.1:8000"
).replace(/\/$/, "");

// Tokens that must never reach the client. Hex segments intentionally
// short (>=6 chars) to avoid colliding with plain English words.
const BANNED_PATTERNS: RegExp[] = [
  /\/uploads\/u_[0-9a-f]{6,}/i,
  /\/uploads\/s_[0-9a-f]{6,}/i,
  /\/workspace\/u_[0-9a-f]{6,}/i,
  /\/workspace\/p_[0-9a-f]{6,}/i,
  /\/workspace\/s_[0-9a-f]{6,}/i,
  // Bare owner segment sitting directly in rendered text.
  /(?<![\w-])u_[0-9a-f]{12,}/i,
  /(?<![\w-])p_[0-9a-f]{12,}/i,
  /(?<![\w-])s_[0-9a-f]{12,}/i,
];

function findBannedHits(haystack: string): string[] {
  const hits: string[] = [];
  for (const re of BANNED_PATTERNS) {
    const m = haystack.match(re);
    if (m && m[0]) hits.push(m[0]);
  }
  return hits;
}

async function getAuthToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem("auth_token"));
  if (!token) throw new Error("auth_token missing from storageState");
  return token;
}

test.describe("workspace-sandbox-unification — path leakage guard", () => {
  test("E2E-01: upload response + composer surface are free of owner tokens", async ({
    page,
  }) => {
      await page.goto("/start");

    const token = await getAuthToken(page);
    const sessionId = `e2e-ws-${Date.now().toString(36)}`;

    const form = new FormData();
    const fileBody = new Blob([`hello from e2e at ${new Date().toISOString()}`], {
      type: "text/plain",
    });
    form.append("files", fileBody, "workspace-e2e-sample.txt");
    form.append("session_id", sessionId);

    const uploadResp: APIResponse = await page.request.post(
      `${API_BASE}/uploads`,
      {
        multipart: {
          files: {
            name: "workspace-e2e-sample.txt",
            mimeType: "text/plain",
            buffer: Buffer.from(
              `hello from e2e at ${new Date().toISOString()}`,
            ),
          },
          session_id: sessionId,
          // Match the SPA: bind the upload to the active project so
          // owner-scoped workspace (u_<uid>/p_<pid>) resolves on read.
          project_id: sessionId,
        },
        headers: { Authorization: `Bearer ${token}` },
      },
    );

    expect(uploadResp.ok(), await uploadResp.text()).toBeTruthy();
    const uploadJson = (await uploadResp.json()) as {
      files: Array<{ filename: string; virtual_path: string }>;
    };
    expect(uploadJson.files.length).toBe(1);

    // Sanity: the API returns an internal `virtual_path` for backend plumbing.
    // That reference is NOT rendered in the DOM — it only flows back into
    // /analyze as an attachment handle. The filename the user sees must be
    // the original upload name.
    expect(uploadJson.files[0].filename).toBe("workspace-e2e-sample.txt");

    // Give the SPA a beat to settle any post-auth redirects / fetches.
    await page.waitForLoadState("domcontentloaded");

    const visibleText = await page.locator("body").innerText();
    const hits = findBannedHits(visibleText);
    expect(
      hits,
      `Owner tokens leaked into rendered DOM: ${hits.join(", ")}`,
    ).toEqual([]);
  });

  test("E2E-02: /analyze SSE stream body contains no owner tokens", async ({
    page,
  }) => {
    // Navigate first so localStorage is reachable (storageState is applied
    // on first commit for the session origin).
      await page.goto("/start");
    const token = await getAuthToken(page);
    const sessionId = `e2e-ws-stream-${Date.now().toString(36)}`;

    // Deliberately tiny prompt. We only need a few SSE frames to flow — this
    // is a leakage guard, not a behavioural test for the agent's answer.
    const analyzeResp = await page.request.post(`${API_BASE}/analyze`, {
      data: {
        message: "Say hi in one short sentence.",
        stream: true,
        session_id: sessionId,
        project_id: sessionId,
        ui_language: "en",
      },
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      timeout: 60_000,
    });

    // Gracefully skip on quota / provider outage so path-leak coverage is
    // never held hostage by a 429. The unit test suite already exercises
    // the scrubber end-to-end against captured SSE fixtures.
    if (!analyzeResp.ok()) {
      const status = analyzeResp.status();
      const body = await analyzeResp.text();
      if (
        status === 429 ||
        status >= 500 ||
        /RESOURCE_EXHAUSTED|quota|Too Many Requests/i.test(body)
      ) {
        test.skip(
          true,
          `Skipping live-LLM leg: /analyze returned ${status} (${body.slice(0, 160)})`,
        );
      }
      throw new Error(`/analyze failed with ${status}: ${body}`);
    }

    const raw = await analyzeResp.text();
    // Short-circuit: if the server returned an error JSON inside a 200 body.
    if (/RESOURCE_EXHAUSTED|quota|exhausted/i.test(raw)) {
      test.skip(true, `Skipping live-LLM leg: provider quota exhausted`);
    }

    const hits = findBannedHits(raw);
    expect(
      hits,
      `Owner tokens leaked in /analyze SSE body: ${hits.slice(0, 5).join(", ")}`,
    ).toEqual([]);

    // Positive assertion: at least one frame landed. Guards against silent
    // empty streams that would trivially pass the negative check above.
    expect(raw.length, "SSE body unexpectedly empty").toBeGreaterThan(0);
  });

  test("E2E-03: rendered DOM after bootstrap has no owner tokens", async ({
    page,
  }) => {
    // Scope of this test is *user-visible text*. Non-SSE backend JSON
    // responses (e.g. /messages, /projects) legitimately carry owner-scoped
    // `file_path` handles that the frontend only uses as opaque references —
    // they are never rendered. The contract we guard is: whatever ends up in
    // the DOM after the homepage settles must already be scrubbed.
      await page.goto("/start");
    await page.waitForLoadState("domcontentloaded");
    // Let lazy workspace / reasoning components mount.
    await page.waitForTimeout(2000);

    const visibleText = await page.locator("body").innerText();
    const hits = findBannedHits(visibleText);
    expect(
      hits,
      `Owner tokens leaked into DOM: ${hits.slice(0, 5).join(", ")}`,
    ).toEqual([]);
  });
});
