import assert from "node:assert"
import test from "node:test"
import { analyzePipeline } from "./ops-check.mjs"

function mkCfg(autofix = {}) {
  return {
    autofix: {
      enabled: false,
      maxLlmCallsPerRun: 5,
      maxLlmCallsPerDay: 100,
      llmVerdictTtl: "24h",
      ...autofix,
    },
    classification: { minOccurrencesForHigh: 5 },
  }
}

test("analyzePipeline: same fingerprint dedupes LLM within one run", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  delete process.env.OPENAI_MODEL
  const prevFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls++
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "low", autofix: false, rationale: "t" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const msg = "DedupTestMessageMarker abc123 unique string"
    const entries = [
      {
        message: msg,
        service: "svc-dedup",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-01-01T00:00:00Z"),
        raw: {},
      },
      {
        message: msg,
        service: "svc-dedup",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-01-01T00:01:00Z"),
        raw: {},
      },
    ]
    const usedLlm = { count: 0 }
    const r = await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm,
      prevLlmVerdicts: {},
      nowMs: Date.now(),
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    assert.strictEqual(fetchCalls, 1)
    assert.strictEqual(r.findings.length, 1)
    assert.strictEqual(r.entryRows.length, 2)
    assert.ok(r.llmStats.cacheHitsRun >= 1)
    assert.strictEqual(r.llmStats.calls, 1)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("analyzePipeline: state verdict cache avoids fetch when fresh", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  delete process.env.OPENAI_MODEL
  const prevFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls++
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "low", autofix: false, rationale: "t" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const msg = "StateCacheTestMarker def456 unique string"
    const entries = [
      {
        message: msg,
        service: "svc-state",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-02-01T00:00:00Z"),
        raw: {},
      },
    ]
    const nowMs = Date.now()
    const used1 = { count: 0 }
    const r1 = await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm: used1,
      prevLlmVerdicts: {},
      nowMs,
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    assert.strictEqual(fetchCalls, 1)
    const fp = Object.keys(r1.llmVerdictsDelta)[0]
    assert.ok(fp)

    fetchCalls = 0
    const used2 = { count: 0 }
    const r2 = await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm: used2,
      prevLlmVerdicts: r1.llmVerdictsDelta,
      nowMs,
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    assert.strictEqual(fetchCalls, 0)
    assert.ok(r2.entryRows.every((row) => String(row.ruleName).includes("state-cache")))
    assert.ok(r2.llmStats.cacheHitsState >= 1)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("analyzePipeline: expired state verdict refetches", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  delete process.env.OPENAI_MODEL
  const prevFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls++
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "medium", autofix: false, rationale: "t2" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const msg = "ExpireCacheMarker ghi789 unique string"
    const entries = [
      {
        message: msg,
        service: "svc-exp",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-03-01T00:00:00Z"),
        raw: {},
      },
    ]
    const nowMs = Date.now()
    const used1 = { count: 0 }
    const r1 = await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm: used1,
      prevLlmVerdicts: {},
      nowMs,
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    const fp = Object.keys(r1.llmVerdictsDelta)[0]
    const stale = { ...r1.llmVerdictsDelta[fp], ts: nowMs - 48 * 3600_000 }
    fetchCalls = 0
    const used2 = { count: 0 }
    await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm: used2,
      prevLlmVerdicts: { [fp]: stale },
      nowMs,
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    assert.strictEqual(fetchCalls, 1)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("analyzePipeline: model mismatch ignores stale verdict", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  process.env.OPENAI_MODEL = "deepseek-ai/DeepSeek-V4-Pro"
  const prevFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls++
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "low", autofix: false, rationale: "t" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const msg = "ModelMismatchMarker jkl012 unique string"
    const entries = [
      {
        message: msg,
        service: "svc-mm",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-04-01T00:00:00Z"),
        raw: {},
      },
    ]
    const nowMs = Date.now()
    const used1 = { count: 0 }
    const r1 = await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm: used1,
      prevLlmVerdicts: {},
      nowMs,
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    const fp = Object.keys(r1.llmVerdictsDelta)[0]
    const wrongModel = { ...r1.llmVerdictsDelta[fp], model: "other-model" }
    fetchCalls = 0
    const used2 = { count: 0 }
    await analyzePipeline({
      cfg: mkCfg(),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm: used2,
      prevLlmVerdicts: { [fp]: wrongModel },
      nowMs,
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    assert.strictEqual(fetchCalls, 1)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
    delete process.env.OPENAI_MODEL
  }
})

test("analyzePipeline: UTC day rollover resets daily usage before cap check", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  delete process.env.OPENAI_MODEL
  const prevFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls++
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "low", autofix: false, rationale: "t" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const msg = "CrossDayUtcMarker pqr678 unique string no heuristic"
    const entries = [
      {
        message: msg,
        service: "svc-crossday",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-06-02T12:00:00.000Z"),
        raw: {},
      },
    ]
    const usedLlm = { count: 0 }
    await analyzePipeline({
      cfg: mkCfg({ maxLlmCallsPerDay: 1 }),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm,
      prevLlmVerdicts: {},
      nowMs: Date.parse("2026-06-02T12:00:00.000Z"),
      llmDailyUsageInitial: { date: "2026-06-01", count: 1 },
    })
    assert.strictEqual(fetchCalls, 1)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})

test("analyzePipeline: zero daily cap skips fetch", async () => {
  process.env.OPENAI_API_KEY = "sk-test"
  const prevFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls++
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ severity: "low", autofix: false, rationale: "t" }),
            },
          },
        ],
      }),
    }
  }
  try {
    const msg = "DailyCapMarker mno345 unique string should not be INFO line"
    const entries = [
      {
        message: msg,
        service: "svc-cap",
        source: "s1",
        stream: "stderr",
        timestamp: new Date("2026-05-01T00:00:00Z"),
        raw: {},
      },
    ]
    const usedLlm = { count: 0 }
    await analyzePipeline({
      cfg: mkCfg({ maxLlmCallsPerDay: 0 }),
      entries,
      rules: [],
      environment: "env",
      project: "p",
      diagnoseMode: false,
      usedLlm,
      prevLlmVerdicts: {},
      nowMs: Date.now(),
      llmDailyUsageInitial: { date: "", count: 0 },
    })
    assert.strictEqual(fetchCalls, 0)
  } finally {
    globalThis.fetch = prevFetch
    delete process.env.OPENAI_API_KEY
  }
})
