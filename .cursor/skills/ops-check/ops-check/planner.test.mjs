/**
 * Planner / dry-run evidence for synthetic fixture configs (review plan Phase 5).
 */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const script = path.join(root, "ops-check", "ops-check.mjs")

function runOpsCheck(args) {
  return spawnSync(process.execPath, [script, ...args], { cwd: root, encoding: "utf8" })
}

function parseMaturePreview(stdout) {
  const m = String(stdout || "").match(
    /--- OPS_CHECK_MATURE_PREVIEW_BEGIN ---([\s\S]*?)--- OPS_CHECK_MATURE_PREVIEW_END ---/,
  )
  assert.ok(m, "OPS_CHECK_MATURE_PREVIEW block missing")
  return JSON.parse(m[1].trim())
}

/** Leading stdout JSON summary (entries/findings counts) precedes diagnostic lines (`source=`). */
function parseTopSummaryJson(stdout) {
  const s = String(stdout || "")
  const src = "\nsource="
  const ix = s.indexOf(src)
  assert.ok(ix >= 0, "expected summary JSON followed by diagnostic `source=` lines")
  const head = s.slice(0, ix)
  const nl = head.lastIndexOf("\n}")
  assert.ok(nl >= 0, "could not find end of summary JSON")
  return JSON.parse(head.slice(0, nl + 2).trim())
}

test("run --dry-run with planner fixture: non-empty findingsPlan + enrichment fields", () => {
  const r = runOpsCheck(["run", "--dry-run", "--config", "ops-check/config.planner-fixture.yaml"])
  assert.equal(r.status, 0, r.stderr)

  const top = parseTopSummaryJson(r.stdout)
  assert.ok(Number(top.entries) >= 3, "expected synthetic log entries")
  assert.ok(Number(top.findings) >= 3)
  assert.ok(top.llmStats && typeof top.llmStats === "object")
  assert.strictEqual(typeof top.llmStats.calls, "number")
  assert.strictEqual(typeof top.llmStats.heuristicSkips, "number")
  assert.strictEqual(typeof top.llmStats.budgetRemainingRun, "number")
  assert.strictEqual(typeof top.llmStats.budgetRemainingDay, "number")

  const j = parseMaturePreview(r.stdout)
  assert.ok(Array.isArray(j.findingsPlan) && j.findingsPlan.length >= 3)

  const routes = j.findingsPlan.map((x) => x.fixRoute)
  assert.ok(routes.includes("template_patch"), `got routes: ${routes.join(",")}`)
  assert.ok(routes.includes("fix_agent_request"))
  assert.ok(routes.includes("issue_only"))

  for (const row of j.findingsPlan) {
    assert.ok(row.plannedAction, "plannedAction missing")
    assert.ok(row.fixRoute, "fixRoute missing")
    assert.ok("routingReason" in row)
    assert.ok(row.testPlan && typeof row.testPlan === "object")
    assert.ok(Array.isArray(row.sideEffectsSkipped))
  }

  const tpl = j.findingsPlan.find((x) => x.fixRoute === "template_patch")
  assert.ok(tpl?.testPlan?.required?.length, "template finding should carry required commands")

  const enr = j.enrichment && typeof j.enrichment === "object" ? j.enrichment : {}
  const values = Object.values(enr).filter(Boolean)
  assert.ok(values.length, "enrichment fingerprints empty")

  for (const e of values) {
    assert.ok(e.routingReason && String(e.routingReason).length > 1, `routingReason: ${e.routingReason}`)
    assert.ok(e.fixRequest && typeof e.fixRequest === "object")
    assert.ok(Array.isArray(e.fixRequest?.allowedEditPaths))
  }

  assert.ok(Number(top.planned.templatePrs) >= 1)
  assert.ok(Number(top.planned.agentFixAttempts) >= 1)
})

test("run --dry-run with no-required test-map: routes missing_required_tests", () => {
  const r = runOpsCheck(["run", "--dry-run", "--config", "ops-check/config.planner-norequired.yaml"])
  assert.equal(r.status, 0, r.stderr)
  const top = parseTopSummaryJson(r.stdout)
  assert.equal(Number(top.findings), 1)
  const j = parseMaturePreview(r.stdout)
  const fp = j.findingsPlan?.[0]
  assert.ok(fp)
  assert.equal(fp.fixRoute, "issue_only")
  assert.equal(fp.routingReason, "missing_required_tests")
})
