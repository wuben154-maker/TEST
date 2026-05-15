import path from "node:path"
import { FORBIDDEN_DOMAIN_KEYS, hitForbiddenDomain } from "./fix-route.mjs"

/** @returns {string[]} relative repo paths */
export function suspectedFilesFromStack(stackTop, repoRoot) {
  if (!stackTop || stackTop === "unknown-frame") return []
  const head = stackTop.includes(":") ? stackTop.slice(0, stackTop.lastIndexOf(":")) : stackTop
  const rel = path.isAbsolute(head)
    ? path.relative(repoRoot, head)
    : head.replace(/^\.?\/?/, "").replace(/\\/g, "/")
  return rel && rel !== "." ? [rel.replace(/\\/g, "/")] : []
}

/** @returns {{ hits: string[], hitRelPaths: string[] }} */
export function forbiddenSignalsForFinding(finding, cfg, repoRoot) {
  /** @type {Set<string>} */
  const hits = new Set()
  const rels = [...suspectedFilesFromStack(finding.stackTop, repoRoot)].filter(Boolean)
  const patterns = Array.isArray(cfg?.autofix?.forbiddenPaths) ? cfg.autofix.forbiddenPaths : []

  for (const rel of rels) {
    const dom = hitForbiddenDomain(rel.replace(/\\/g, "/"))
    if (dom) hits.add(dom)
    for (const pat of patterns) {
      try {
        const re = globToForbiddenRegex(pat)
        if (re.test(rel.replace(/\\/g, "/"))) hits.add("forbidden_glob_match")
      } catch {
        /* ignore bad pattern */
      }
    }
  }
  return { hits: [...hits], hitRelPaths: rels }
}

function globToForbiddenRegex(pat) {
  const p = pat.replace(/\\/g, "/")
  return new RegExp(
    "^" +
      p
        .replace(/[.+^${}()|[\]\\]/g, "\\$&")
        .replace(/\*\*/g, ".*")
        .replace(/\*/g, "[^/]*") +
      "$",
    "i",
  )
}

/**
 * Builds the payload embedded in Issues/PRs.
 * Secrets must never be included beyond redacted excerpts already on finding.
 *
 * @param {{
 * finding: any,
 * cfg: any,
 * fixRoute: string,
 * testPlan: any,
 * allowedEditPaths: string[],
 * forbiddenEditPaths: string[],
 * forbiddenDomainsTriggered: string[],
 * routingReason?: string,
 * }} input
 */
export function buildFixRequest({
  finding,
  cfg,
  fixRoute,
  testPlan,
  allowedEditPaths,
  forbiddenEditPaths,
  forbiddenDomainsTriggered,
  routingReason,
}) {
  const project = cfg.project || "unknown"
  const environment = cfg.environment || "unknown"
  const severity = finding.severity || "medium"
  const suspected = uniq([
    ...suspectedFilesFromStack(finding.stackTop, process.cwd()),
    ...(finding.suspectedFiles || []),
  ])

  /** @type {typeof FORBIDDEN_DOMAIN_KEYS[number][]} */
  const fd = []
  for (const x of forbiddenDomainsTriggered || []) {
    if (FORBIDDEN_DOMAIN_KEYS.includes(x)) fd.push(x)
  }

  return {
    fingerprint: finding.fingerprint,
    project,
    environment,
    severity,
    fixRoute,
    service: finding.service || "unknown-service",
    errorSummary: String(finding.msgTpl || "").slice(0, 500),
    logEvidence: (finding.messages || []).slice(0, 5).map((m) => String(m || "").slice(0, 300)),
    stackTop: finding.stackTop || "unknown-frame",
    suspectedFiles: suspected,
    allowedEditPaths: allowedEditPaths || [],
    forbiddenEditPaths: forbiddenEditPaths || [],
    forbiddenDomains: fd.length ? fd : [...FORBIDDEN_DOMAIN_KEYS],
    testPlan: sanitizeTestPlanForSchema(testPlan),
    acceptanceCriteria: uniq([
      "All required verification commands exit 0",
      "Changes stay inside allowedEditPaths",
      routingReason ? `Routing: ${routingReason}` : null,
      "Secrets are not logged or introduced",
      "Reviewer must approve; ops-check never merges",
    ]).filter(Boolean),
  }
}

function uniq(xs) {
  return [...new Set((xs || []).filter(Boolean))]
}

/** Align with fix-request.schema.json */
function sanitizeTestPlanForSchema(tp) {
  const out = tp || {}
  return {
    required: uniq(out.required || []),
    optional: uniq(out.optional || []),
    unit: uniq(out.unit || []),
    integration: uniq(out.integration || []),
    e2e: uniq(out.e2e || []),
    smoke: uniq(out.smoke || []),
    full: uniq(out.full || []),
  }
}

/** Lightweight structural validator (no external JSON-schema engine). */
export function validateFixRequestShape(req) {
  const errs = []
  const need = [
    "fingerprint",
    "project",
    "environment",
    "severity",
    "fixRoute",
    "service",
    "errorSummary",
    "logEvidence",
    "stackTop",
    "suspectedFiles",
    "allowedEditPaths",
    "forbiddenEditPaths",
    "forbiddenDomains",
    "testPlan",
    "acceptanceCriteria",
  ]
  for (const k of need) {
    if (!(k in req)) errs.push(`missing:${k}`)
  }
  const allowedRoutes = [
    "template_patch",
    "fix_agent_request",
    "issue_only",
    "notify_only",
    "silent",
    "ignore_or_recover",
  ]
  if (req.fixRoute && !allowedRoutes.includes(req.fixRoute)) errs.push(`fixRoute:${req.fixRoute}`)
  if (!req.testPlan || typeof req.testPlan !== "object") errs.push("testPlan:object_required")
  else {
    ;["required", "optional", "unit", "integration", "e2e", "smoke", "full"].forEach((k) => {
      const v = req.testPlan[k]
      if (v != null && !Array.isArray(v)) errs.push(`testPlan.${k}:array_expected`)
    })
    if (!Array.isArray(req.testPlan.required)) errs.push("testPlan.required:array_expected")
  }
  return errs
}
