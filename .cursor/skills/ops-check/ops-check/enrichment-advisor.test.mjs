import assert from "node:assert"
import path from "node:path"
import test from "node:test"
import { applyAdvisorBatchSync, buildFingerprintEnrichment, consultAdvisorsAndReroute } from "./ops-check.mjs"

const testMapDoc = {
  defaults: {
    lint: ["echo lint"],
    unit: ["echo unit"],
    smoke: [],
    e2e: [],
    integration: [],
    full: [],
  },
  modules: {
    fixturelow: {
      paths: ["ops-check/fixtures/**"],
      unit: ["echo fixture-unit"],
      risk: "low",
    },
  },
  testPolicy: {
    required: ["lint", "related-unit"],
    optional: [],
    passRule: "all-required-pass",
  },
}

const cfgOff = {
  autofix: { enabled: true, forbiddenPaths: [], verificationCommands: ["echo ok"] },
  fixAgent: { enabled: true },
  classification: { recurrenceEscalation: true },
  routingAdvisor: { enabled: false, minConfidence: 0.6, maxCallsPerRun: 5 },
  project: "p",
  environment: "e",
}

function minimalFinding(fp) {
  const stackTop = `${path.join("ops-check", "fixtures", "low-risk.tsx")}:10`
  return {
    fingerprint: fp,
    service: "svc",
    severity: "low",
    ruleName: "r1",
    messages: ['Cannot read property "x" of undefined'],
    sources: new Set(["s"]),
    autofixAllowed: true,
    msgTpl: 'Cannot read property "x" of undefined',
    stackTop,
    rule: { autofix: true, targetRoute: "template_patch" },
    occurrenceTimes: [Date.now()],
  }
}

test("default advisor off: enrichment.advisor.consulted false, pending empty", () => {
  const f = minimalFinding("a1")
  const { enrichment, pendingAdvisor } = buildFingerprintEnrichment({
    cfg: cfgOff,
    findings: [f],
    state: { fingerprints: {} },
    testMapDoc,
    repoRoot: process.cwd(),
    runFlags: { advisorAllowed: false },
  })
  const e = enrichment[f.fingerprint]
  assert.strictEqual(e.advisor?.consulted, false)
  assert.strictEqual(pendingAdvisor.length, 0)
})

test("applyAdvisorBatchSync mock veto → issue_only", () => {
  const fp = "vf1"
  const f = minimalFinding(fp)
  const cfgOn = { ...cfgOff, routingAdvisor: { enabled: true, minConfidence: 0.6, maxCallsPerRun: 5 } }
  const { enrichment, pendingAdvisor } = buildFingerprintEnrichment({
    cfg: cfgOn,
    findings: [f],
    state: { fingerprints: {} },
    testMapDoc,
    repoRoot: process.cwd(),
    runFlags: { advisorAllowed: true },
  })
  assert.ok(pendingAdvisor.length >= 1)
  const stats = { consulted: 0, vetoed: 0, passed: 0, lowConfidence: 0, errors: 0 }
  const verdicts = new Map([
    [fp, { veto: true, code: "path_looks_sensitive", confidence: 0.9, rationale: "" }],
  ])
  applyAdvisorBatchSync({ cfg: cfgOn, enrichment, pendingAdvisor, verdicts, stats })
  assert.strictEqual(enrichment[fp].fixRoute, "issue_only")
  assert.ok(String(enrichment[fp].routingReason).startsWith("llm_veto:"))
})

test("applyAdvisorBatchSync mock pass → route unchanged + advisorPassed", () => {
  const fp = "pf1"
  const f = minimalFinding(fp)
  const cfgOn = { ...cfgOff, routingAdvisor: { enabled: true, minConfidence: 0.6, maxCallsPerRun: 5 } }
  const { enrichment, pendingAdvisor } = buildFingerprintEnrichment({
    cfg: cfgOn,
    findings: [f],
    state: { fingerprints: {} },
    testMapDoc,
    repoRoot: process.cwd(),
    runFlags: { advisorAllowed: true },
  })
  const beforeRoute = enrichment[fp].fixRoute
  const stats = { consulted: 0, vetoed: 0, passed: 0, lowConfidence: 0, errors: 0 }
  const verdicts = new Map([[fp, { veto: false, code: "ok", confidence: 0.95, rationale: "" }]])
  applyAdvisorBatchSync({ cfg: cfgOn, enrichment, pendingAdvisor, verdicts, stats })
  assert.strictEqual(enrichment[fp].fixRoute, beforeRoute)
  assert.strictEqual(enrichment[fp].advisor?.consulted, true)
  assert.strictEqual(enrichment[fp].advisor?.veto, false)
})

test("consultAdvisorsAndReroute skips HTTP when advisorAllowed false", async () => {
  const fp = "http1"
  const f = minimalFinding(fp)
  const cfgOn = { ...cfgOff, routingAdvisor: { enabled: true, minConfidence: 0.6, maxCallsPerRun: 5 } }
  const { enrichment, pendingAdvisor } = buildFingerprintEnrichment({
    cfg: cfgOn,
    findings: [f],
    state: { fingerprints: {} },
    testMapDoc,
    repoRoot: process.cwd(),
    runFlags: { advisorAllowed: false },
  })
  const orig = globalThis.fetch
  let n = 0
  globalThis.fetch = async () => {
    n++
    return new Response("{}")
  }
  try {
    await consultAdvisorsAndReroute({
      cfg: cfgOn,
      findings: [f],
      enrichment,
      pendingAdvisor,
      runFlags: { advisorAllowed: false },
      state: {},
      llmDailyUsage: { date: "", count: 0 },
    })
    assert.strictEqual(n, 0)
  } finally {
    globalThis.fetch = orig
  }
})
