import assert from "node:assert"
import test from "node:test"
import process from "node:process"
import { consultAdvisorsAndReroute } from "./ops-check.mjs"

const cfgBase = {
  autofix: { enabled: true, maxLlmCallsPerDay: 100, forbiddenPaths: [], verificationCommands: ["echo ok"] },
  fixAgent: { enabled: true },
  classification: { recurrenceEscalation: true },
  routingAdvisor: { enabled: true, minConfidence: 0.6, maxCallsPerRun: 5, verdictTtl: "6h" },
  project: "p",
  environment: "e",
}

function fixture(fp) {
  const finding = {
    fingerprint: fp,
    service: "s",
    severity: "low",
    ruleName: "r",
    messages: ["m"],
    sources: new Set(["x"]),
    autofixAllowed: true,
    msgTpl: "m",
    stackTop: "src/a.ts:1",
    rule: { autofix: true, targetRoute: "template_patch" },
    occurrenceTimes: [Date.now()],
  }
  const testPlan = { required: ["echo ok"], optional: [], unit: [], e2e: [], smoke: [], full: [], integration: [] }
  const fixRequest = {
    fingerprint: fp,
    project: "p",
    environment: "e",
    severity: "low",
    fixRoute: "template_patch",
    service: "s",
    errorSummary: "m",
    logEvidence: [],
    stackTop: "src/a.ts:1",
    suspectedFiles: [],
    allowedEditPaths: ["src"],
    forbiddenEditPaths: [],
    forbiddenDomains: [],
    testPlan,
    acceptanceCriteria: [],
  }
  const enrichment = {
    [fp]: {
      fixRoute: "template_patch",
      routingReason: "r",
      testPlan,
      fixRequest,
      signals: {},
      advisor: { consulted: false },
    },
  }
  const pendingAdvisor = [
    { fingerprint: fp, proposed: { fixRoute: "template_patch", routingReason: "r" }, finding, fixRequest },
  ]
  return { finding, enrichment, pendingAdvisor }
}

test("advisor cache: fresh cache entry skips HTTP", async () => {
  const prevModel = process.env.OPENAI_MODEL
  process.env.OPENAI_MODEL = "gpt-test"
  const fp = "cache-hit"
  const { finding, enrichment, pendingAdvisor } = fixture(fp)
  let fetches = 0
  const orig = globalThis.fetch
  globalThis.fetch = async () => {
    fetches++
    return new Response("{}", { status: 500 })
  }
  const now = Date.now()
  try {
    process.env.OPENAI_API_KEY = "k"
    await consultAdvisorsAndReroute({
      cfg: cfgBase,
      findings: [finding],
      enrichment,
      pendingAdvisor,
      runFlags: { advisorAllowed: true },
      state: {
        advisorVerdicts: {
          [fp]: {
            veto: false,
            code: "ok",
            confidence: 0.95,
            model: "gpt-test",
            candidateRoute: "template_patch",
            ts: now,
            ttlMs: 3600_000,
          },
        },
      },
      nowMs: now + 60_000,
      llmDailyUsage: { date: "", count: 0 },
    })
    assert.strictEqual(fetches, 0)
  } finally {
    globalThis.fetch = orig
    delete process.env.OPENAI_API_KEY
    if (prevModel === undefined) delete process.env.OPENAI_MODEL
    else process.env.OPENAI_MODEL = prevModel
  }
})

test("advisor cache: expired TTL refetches", async () => {
  const prevModel = process.env.OPENAI_MODEL
  process.env.OPENAI_MODEL = "gpt-test"
  const fp = "cache-exp"
  const { finding, enrichment, pendingAdvisor } = fixture(fp)
  let fetches = 0
  const orig = globalThis.fetch
  globalThis.fetch = async () => {
    fetches++
    return new Response(
      JSON.stringify({
        choices: [
          { message: { content: JSON.stringify({ veto: false, code: "ok", confidence: 0.95, rationale: "" }) } },
        ],
      }),
    )
  }
  const now = Date.now()
  try {
    process.env.OPENAI_API_KEY = "k"
    await consultAdvisorsAndReroute({
      cfg: cfgBase,
      findings: [finding],
      enrichment,
      pendingAdvisor,
      runFlags: { advisorAllowed: true },
      state: {
        advisorVerdicts: {
          [fp]: {
            veto: false,
            code: "ok",
            confidence: 0.95,
            model: "gpt-test",
            candidateRoute: "template_patch",
            ts: now - 10_000_000,
            ttlMs: 1000,
          },
        },
      },
      nowMs: now,
      llmDailyUsage: { date: "", count: 0 },
    })
    assert.strictEqual(fetches, 1)
  } finally {
    globalThis.fetch = orig
    delete process.env.OPENAI_API_KEY
    if (prevModel === undefined) delete process.env.OPENAI_MODEL
    else process.env.OPENAI_MODEL = prevModel
  }
})

test("advisor cache: model mismatch ignores cache", async () => {
  const prevModel = process.env.OPENAI_MODEL
  process.env.OPENAI_MODEL = "gpt-new"
  const fp = "cache-model"
  const { finding, enrichment, pendingAdvisor } = fixture(fp)
  let fetches = 0
  const orig = globalThis.fetch
  globalThis.fetch = async () => {
    fetches++
    return new Response(
      JSON.stringify({
        choices: [
          { message: { content: JSON.stringify({ veto: false, code: "ok", confidence: 0.95, rationale: "" }) } },
        ],
      }),
    )
  }
  const now = Date.now()
  try {
    process.env.OPENAI_API_KEY = "k"
    await consultAdvisorsAndReroute({
      cfg: cfgBase,
      findings: [finding],
      enrichment,
      pendingAdvisor,
      runFlags: { advisorAllowed: true },
      state: {
        advisorVerdicts: {
          [fp]: {
            veto: false,
            code: "ok",
            confidence: 0.95,
            model: "gpt-old",
            candidateRoute: "template_patch",
            ts: now,
            ttlMs: 3600_000,
          },
        },
      },
      nowMs: now + 1000,
      llmDailyUsage: { date: "", count: 0 },
    })
    assert.strictEqual(fetches, 1)
  } finally {
    globalThis.fetch = orig
    delete process.env.OPENAI_API_KEY
    if (prevModel === undefined) delete process.env.OPENAI_MODEL
    else process.env.OPENAI_MODEL = prevModel
  }
})

test("advisor cache: candidateRoute mismatch ignores cache", async () => {
  const prevModel = process.env.OPENAI_MODEL
  process.env.OPENAI_MODEL = "gpt-test"
  const fp = "cache-route"
  const { finding, enrichment, pendingAdvisor } = fixture(fp)
  let fetches = 0
  const orig = globalThis.fetch
  globalThis.fetch = async () => {
    fetches++
    return new Response(
      JSON.stringify({
        choices: [
          { message: { content: JSON.stringify({ veto: false, code: "ok", confidence: 0.95, rationale: "" }) } },
        ],
      }),
    )
  }
  const now = Date.now()
  try {
    process.env.OPENAI_API_KEY = "k"
    await consultAdvisorsAndReroute({
      cfg: cfgBase,
      findings: [finding],
      enrichment,
      pendingAdvisor,
      runFlags: { advisorAllowed: true },
      state: {
        advisorVerdicts: {
          [fp]: {
            veto: false,
            code: "ok",
            confidence: 0.95,
            model: "gpt-test",
            candidateRoute: "fix_agent_request",
            ts: now,
            ttlMs: 3600_000,
          },
        },
      },
      nowMs: now + 1000,
      llmDailyUsage: { date: "", count: 0 },
    })
    assert.strictEqual(fetches, 1)
  } finally {
    globalThis.fetch = orig
    delete process.env.OPENAI_API_KEY
    if (prevModel === undefined) delete process.env.OPENAI_MODEL
    else process.env.OPENAI_MODEL = prevModel
  }
})
