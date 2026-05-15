import test from "node:test"
import assert from "node:assert"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { computeFixRoute, hitForbiddenDomain, severityRank } from "./lib/fix-route.mjs"
import { minimatchLite, selectTests, discoverE2E } from "./lib/test-selector.mjs"
import { buildFixRequest, validateFixRequestShape, forbiddenSignalsForFinding } from "./lib/fix-request.mjs"
import { runTieredVerification } from "./lib/verification-tier.mjs"

test("hitForbiddenDomain flags auth/secrets paths", () => {
  assert.strictEqual(hitForbiddenDomain("src/auth/login.ts"), "auth")
  assert.strictEqual(hitForbiddenDomain("billing/invoice.rb"), "billing")
})

test("computeFixRoute forces issue_only for recurrence and critical/high", () => {
  const base = {
    autofixEnabled: true,
    agentEnabled: false,
    hasTemplatePatch: true,
    hasRequiredTests: true,
    recurrence: false,
    forbiddenGlobMatch: false,
    forbiddenDomainHits: [],
    prevFingerprintState: {},
  }
  const low = {
    autofixAllowed: true,
    severity: "low",
    fingerprint: "x",
    messages: [],
    sources: new Set(["a"]),
  }
  const rLow = computeFixRoute({ ...base, finding: low })
  assert.strictEqual(rLow.fixRoute, "template_patch")

  const critical = { ...low, severity: "critical" }
  const rCrit = computeFixRoute({
    ...base,
    finding: critical,
    hasTemplatePatch: true,
    hasRequiredTests: true,
  })
  assert.strictEqual(rCrit.fixRoute, "issue_only")
  assert.match(rCrit.reason, /severity_critical/)

  const rRec = computeFixRoute({
    ...base,
    recurrence: true,
    finding: low,
  })
  assert.strictEqual(rRec.fixRoute, "issue_only")
})

test("selectTests merges module commands and respects passRule", () => {
  const testMapDoc = {
    defaults: { lint: ["echo lint"], smoke: ["echo smoke"], unit: ["echo unit"] },
    modules: {
      dash: {
        paths: ["src/dashboard/**"],
        unit: ["echo dash-unit"],
        e2e: ["echo dash-e2e"],
        risk: "medium",
      },
    },
    testPolicy: {
      required: ["lint", "related-unit", "related-e2e"],
      optional: [],
      passRule: "all-required-pass",
    },
  }
  const finding = {
    stackTop: `${path.join("src", "dashboard", "widget.tsx")}:10`,
    fingerprint: "fp",
    severity: "low",
  }
  const plan = selectTests({
    finding,
    testMapDoc,
    configPolicy: testMapDoc.testPolicy,
    fixRoute: "template_patch",
  })
  assert.ok(plan.required.length > 0)
  assert.strictEqual(plan.passRule, "all-required-pass")
  assert.ok(plan.reasons.some((s) => s.includes("dashboard")))
})

test("buildFixRequest + validateFixRequestShape", () => {
  const fr = buildFixRequest({
    finding: {
      fingerprint: "abc123",
      service: "api",
      severity: "medium",
      msgTpl: "boom",
      messages: ["e1"],
      stackTop: "src/x.ts:1",
    },
    cfg: { project: "p", environment: "stg", autofix: { forbiddenPaths: [] } },
    fixRoute: "fix_agent_request",
    testPlan: { required: ["echo"], optional: [], unit: [], e2e: [], smoke: [], full: [], integration: [] },
    allowedEditPaths: ["src/x.ts"],
    forbiddenEditPaths: [],
    forbiddenDomainsTriggered: [],
    routingReason: "test",
  })
  assert.deepStrictEqual(validateFixRequestShape(fr), [])
})

test("forbiddenSignalsForFinding respects forbiddenPaths globs", () => {
  const cfg = { autofix: { forbiddenPaths: ["**/secrets/**"] } }
  const finding = { stackTop: `${path.join("pkg", "secrets", "vault.ts")}:2` }
  const sig = forbiddenSignalsForFinding(finding, cfg, "/tmp/repo")
  assert.ok(sig.hits.includes("forbidden_glob_match") || sig.hits.includes("secrets"))
})

test("runTieredVerification: all required must pass", () => {
  const cwd = os.tmpdir()
  const ok = runTieredVerification(
    {
      required: [
        `${process.execPath} -e process.exit(0)`,
        `${process.execPath} -e process.exit(0)`,
      ],
      optional: [],
    },
    [],
    cwd,
  )
  assert.strictEqual(ok.ok, true)

  const bad = runTieredVerification({ required: [`${process.execPath} -e process.exit(1)`] }, [], cwd)
  assert.strictEqual(bad.ok, false)
})

test("runTieredVerification optional failure still allows ok when required passed", () => {
  const cwd = os.tmpdir()
  const r = runTieredVerification(
    {
      required: [`${process.execPath} -e process.exit(0)`],
      optional: [`${process.execPath} -e process.exit(2)`],
    },
    [],
    cwd,
  )
  assert.strictEqual(r.ok, true)
  assert.strictEqual(r.tier, "required-pass_optional-failed")
})

test("minimatchLite basic", () => {
  assert.strictEqual(minimatchLite("src/dashboard/foo.tsx", "src/dashboard/**"), true)
})

test("discoverE2E yields note when repo has no e2e artifacts", async () => {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
  const rep = await discoverE2E(repoRoot, {})
  assert.strictEqual(rep.found, false)
  assert.ok(rep.note)
})

test("runTieredVerification fails when required list is empty", () => {
  const empty = runTieredVerification({ required: [] }, [], os.tmpdir())
  assert.strictEqual(empty.ok, false)
  assert.match(empty.reason || "", /no required verification/i)

  const noFallback = runTieredVerification(null, [], os.tmpdir())
  assert.strictEqual(noFallback.ok, false)
})

test("severityRank numeric order", () => {
  assert.ok(severityRank("critical") > severityRank("high"))
})
