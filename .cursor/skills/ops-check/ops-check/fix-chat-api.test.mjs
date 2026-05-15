/**
 * ModelScope chat Fix Agent — writes allowed paths from mocked completions.
 */
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { runChatCompletionsFixAgent } from "./lib/fix-chat-api.mjs"

test("runChatCompletionsFixAgent applies JSON files response", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wt-chat-fix-"))
  fs.mkdirSync(path.join(dir, "src"), { recursive: true })
  fs.writeFileSync(path.join(dir, "src", "a.ts"), "broken\n", "utf8")

  const fp = "abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234"
  const reqPath = path.join(dir, "req.json")
  fs.writeFileSync(
    reqPath,
    JSON.stringify({
      fingerprint: fp,
      project: "p",
      environment: "e",
      severity: "high",
      fixRoute: "fix_agent_request",
      service: "svc",
      errorSummary: "fix me",
      logEvidence: [],
      stackTop: "src/a.ts:1:1",
      suspectedFiles: ["src/a.ts"],
      allowedEditPaths: ["src/**"],
      forbiddenEditPaths: [],
      forbiddenDomains: [],
      testPlan: {
        required: [],
        optional: [],
        unit: [],
        integration: [],
        e2e: [],
        smoke: [],
        full: [],
      },
      acceptanceCriteria: [],
    }),
    "utf8",
  )

  const prevFetch = globalThis.fetch
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({ files: [{ path: "src/a.ts", content: "fixed\n" }] }),
          },
        },
      ],
    }),
  })
  process.env.TEST_MODELSCOPE_KEY = "dummy-key-for-test"
  try {
    const r = await runChatCompletionsFixAgent(dir, reqPath, {
      baseUrl: "https://api-inference.modelscope.cn/v1",
      apiKeyEnv: "TEST_MODELSCOPE_KEY",
      model: "deepseek-ai/DeepSeek-V4-Pro",
    })
    assert.equal(r.ok, true)
    assert.equal(fs.readFileSync(path.join(dir, "src", "a.ts"), "utf8"), "fixed\n")
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.TEST_MODELSCOPE_KEY
  }
})
