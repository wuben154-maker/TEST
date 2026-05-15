import assert from "node:assert"
import test from "node:test"
import { buildLlmPayload, llmDiagnose, shouldAskLlm } from "./lib/llm-client.mjs"

const baseCfg = { autofix: { maxLlmCallsPerRun: 3, maxLlmCallsPerDay: 100 } }

test("buildLlmPayload truncates msg to <=240", () => {
  const long = "x".repeat(400)
  const p = buildLlmPayload({ service: "s", stackTop: "f", summary: long })
  assert.ok(p.msg.length <= 240)
})

test("buildLlmPayload user JSON shape is svc, frame, msg", () => {
  const p = buildLlmPayload({ service: "svc", stackTop: "st", summary: "hi" })
  assert.deepStrictEqual(Object.keys(p).sort(), ["frame", "msg", "svc"])
})

test("buildLlmPayload redacts IP and UUID in summary", () => {
  const p = buildLlmPayload({
    service: "svc",
    stackTop: "st",
    summary: "seen 192.168.1.1 and 550e8400-e29b-41d4-a716-446655440000",
  })
  assert.match(p.msg, /\[REDACTED_IP\]/)
  assert.match(p.msg, /\[REDACTED_UUID\]/)
})

test("shouldAskLlm: INFO without exception keywords", () => {
  const r = shouldAskLlm('[INFO] startup complete probe scheduled')
  assert.ok(r)
  assert.strictEqual(r.source, "heuristic-skip")
})

test("shouldAskLlm: HTTP 200 style line", () => {
  const r = shouldAskLlm('HTTP/1.1" 200 OK GET /health')
  assert.ok(r)
})

test("shouldAskLlm: traceback triggers LLM path", () => {
  assert.strictEqual(shouldAskLlm("Traceback (most recent call last)"), null)
})

test("shouldAskLlm: timeout triggers LLM path", () => {
  assert.strictEqual(shouldAskLlm("upstream timeout connecting"), null)
})

test("shouldAskLlm: 中文错误 triggers LLM path", () => {
  assert.strictEqual(shouldAskLlm("发生错误：连接失败"), null)
})

test("shouldAskLlm: empty string heuristic skip", () => {
  const r = shouldAskLlm("")
  assert.ok(r)
  assert.strictEqual(r.source, "heuristic-skip")
})

test("llmDiagnose: no OPENAI_API_KEY does not fetch", async () => {
  const prevKey = process.env.OPENAI_API_KEY
  const prevFetch = globalThis.fetch
  delete process.env.OPENAI_API_KEY
  let called = false
  globalThis.fetch = async () => {
    called = true
    return { ok: true, json: async () => ({ choices: [{ message: { content: "{}" } }] }) }
  }
  try {
    const used = { count: 0 }
    await llmDiagnose({ cfg: baseCfg, summary: "e", stackTop: "x", service: "s" }, used)
    assert.strictEqual(called, false)
    assert.strictEqual(used.count, 0)
  } finally {
    globalThis.fetch = prevFetch
    if (prevKey !== undefined) process.env.OPENAI_API_KEY = prevKey
    else delete process.env.OPENAI_API_KEY
  }
})

test("llmDiagnose: run budget exhausted skips fetch", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  const prevFetch = globalThis.fetch
  let called = false
  globalThis.fetch = async () => {
    called = true
    return { ok: true, json: async () => ({}) }
  }
  try {
    const used = { count: 3 }
    await llmDiagnose({ cfg: baseCfg, summary: "e", stackTop: "x", service: "s" }, used)
    assert.strictEqual(called, false)
    assert.strictEqual(used.count, 3)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("llmDiagnose: HTTP 200 JSON yields severity and autofix", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  const prevFetch = globalThis.fetch
  globalThis.fetch = async (_url, opts) => {
    const body = JSON.parse(opts.body)
    const user = body.messages.find((m) => m.role === "user")
    assert.ok(user)
    const parsed = JSON.parse(user.content)
    assert.deepStrictEqual(Object.keys(parsed).sort(), ["frame", "msg", "svc"])
    assert.ok(body.max_tokens === 128)
    assert.ok(body.response_format?.type === "json_object")
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "high", autofix: true, rationale: "ok" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const used = { count: 0 }
    const r = await llmDiagnose(
      { cfg: baseCfg, summary: "err", stackTop: "f.ts:1", service: "svc1" },
      used,
      { dailyUsage: { date: "2099-01-01", count: 0 }, maxPerDay: 100, nowMs: Date.now() },
    )
    assert.strictEqual(r.severity, "high")
    assert.strictEqual(r.autofix, true)
    assert.strictEqual(r._llmOk, true)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("llmDiagnose: HTTP 500 returns medium autofix false", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  const prevFetch = globalThis.fetch
  globalThis.fetch = async () => ({ ok: false, status: 500 })
  try {
    const used = { count: 0 }
    const r = await llmDiagnose({ cfg: baseCfg, summary: "e", stackTop: "x", service: "s" }, used)
    assert.strictEqual(r.severity, "medium")
    assert.strictEqual(r.autofix, false)
    assert.ok(String(r.rationale).includes("500"))
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("llmDiagnose: non-JSON body returns medium autofix false", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  const prevFetch = globalThis.fetch
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ choices: [{ message: { content: "not-json" } }] }),
  })
  try {
    const used = { count: 0 }
    const r = await llmDiagnose({ cfg: baseCfg, summary: "e", stackTop: "x", service: "s" }, used)
    assert.strictEqual(r.severity, "medium")
    assert.strictEqual(r.autofix, false)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})
