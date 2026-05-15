import assert from "node:assert"
import test from "node:test"
import {
  applyAdvice,
  buildAdvisorPayload,
  shouldConsultAdvisor,
  validateAdvisorOutput,
} from "./lib/route-advisor.mjs"

const cfgBase = {
  routingAdvisor: { enabled: true, minConfidence: 0.6, maxCallsPerRun: 5 },
}

test("buildAdvisorPayload truncates and filters paths", () => {
  const finding = {
    service: "S".repeat(80),
    stackTop: `a${"\n"}b:${120}`,
    ruleName: "R".repeat(100),
    severity: "low",
    rule: { templateId: "T".repeat(90) },
  }
  const fixRequest = {
    allowedEditPaths: [
      "src/ok.ts",
      "../bad",
      "<script>x",
      "",
      "a".repeat(200),
      "also/ok.py",
    ],
  }
  const p = buildAdvisorPayload({
    finding,
    candidate: "template_patch",
    fixRequest,
  })
  assert.strictEqual(p.svc.length, 64)
  assert.strictEqual(p.frame.length <= 120, true)
  assert.strictEqual(p.ruleName != null && p.ruleName.length <= 64, true)
  assert.strictEqual(p.tplId != null && p.tplId.length <= 64, true)
  assert.strictEqual(p.paths.length <= 10, true)
  assert.ok(p.paths.every((x) => x.length <= 120))
  assert.ok(p.paths.includes("src/ok.ts") || p.paths.includes("also/ok.py"))
})

test("validateAdvisorOutput accepts valid object", () => {
  const v = validateAdvisorOutput({
    veto: false,
    code: "ok",
    confidence: 0.9,
    rationale: "fine",
  })
  assert.strictEqual(v.ok, true)
})

test("validateAdvisorOutput rejects missing veto", () => {
  const v = validateAdvisorOutput({ code: "ok", confidence: 1, rationale: "" })
  assert.strictEqual(v.ok, false)
})

test("validateAdvisorOutput rejects bad code", () => {
  const v = validateAdvisorOutput({
    veto: false,
    code: "nope",
    confidence: 1,
    rationale: "",
  })
  assert.strictEqual(v.ok, false)
})

test("validateAdvisorOutput rejects confidence out of range", () => {
  const v = validateAdvisorOutput({
    veto: false,
    code: "ok",
    confidence: 1.5,
    rationale: "",
  })
  assert.strictEqual(v.ok, false)
})

test("validateAdvisorOutput rejects extra keys", () => {
  const v = validateAdvisorOutput({
    veto: false,
    code: "ok",
    confidence: 1,
    rationale: "",
    extra: 1,
  })
  assert.strictEqual(v.ok, false)
})

test("applyAdvice null advice → issue_only llm_advisor_invalid", () => {
  const r = applyAdvice({
    proposed: { fixRoute: "template_patch", routingReason: "x" },
    advice: null,
    cfg: cfgBase,
  })
  assert.strictEqual(r.fixRoute, "issue_only")
  assert.strictEqual(r.reason, "llm_advisor_invalid")
})

test("applyAdvice veto true", () => {
  const r = applyAdvice({
    proposed: { fixRoute: "fix_agent_request", routingReason: "x" },
    advice: { veto: true, code: "path_looks_sensitive", confidence: 0.9, rationale: "" },
    cfg: cfgBase,
  })
  assert.strictEqual(r.fixRoute, "issue_only")
  assert.strictEqual(r.reason, "llm_veto:path_looks_sensitive")
})

test("applyAdvice low confidence", () => {
  const r = applyAdvice({
    proposed: { fixRoute: "template_patch", routingReason: "x" },
    advice: { veto: false, code: "ok", confidence: 0.4, rationale: "" },
    cfg: cfgBase,
  })
  assert.strictEqual(r.fixRoute, "issue_only")
  assert.ok(String(r.reason).startsWith("llm_low_confidence:"))
})

test("applyAdvice pass", () => {
  const r = applyAdvice({
    proposed: { fixRoute: "template_patch", routingReason: "tpl" },
    advice: { veto: false, code: "ok", confidence: 0.9, rationale: "" },
    cfg: cfgBase,
  })
  assert.strictEqual(r.fixRoute, "template_patch")
  assert.strictEqual(r.routingReason, "tpl")
  assert.strictEqual(r.advisorPassed, true)
})

test("applyAdvice issue_only proposed unchanged (no upgrade)", () => {
  const r = applyAdvice({
    proposed: { fixRoute: "issue_only", routingReason: "rule" },
    advice: { veto: false, code: "ok", confidence: 1, rationale: "" },
    cfg: cfgBase,
  })
  assert.strictEqual(r.fixRoute, "issue_only")
  assert.strictEqual(r.routingReason, "rule")
})

test("shouldConsultAdvisor gate", () => {
  assert.strictEqual(
    shouldConsultAdvisor({
      cfg: { routingAdvisor: { enabled: true } },
      runFlags: { advisorAllowed: true },
      candidateRoute: "template_patch",
    }),
    true,
  )
  assert.strictEqual(
    shouldConsultAdvisor({
      cfg: { routingAdvisor: { enabled: false } },
      runFlags: { advisorAllowed: true },
      candidateRoute: "template_patch",
    }),
    false,
  )
})
