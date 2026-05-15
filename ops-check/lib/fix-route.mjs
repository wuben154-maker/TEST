/** Routes findings to template / agent / issue-only buckets (code-enforced gates). */

export const FORBIDDEN_DOMAIN_KEYS = ["auth", "billing", "secrets", "migrations", "infra", "permissions"]

export const ROUTE_VALUES = [
  "template_patch",
  "fix_agent_request",
  "issue_only",
  "notify_only",
  "silent",
]

/** @returns {typeof FORBIDDEN_DOMAIN_KEYS[number] | null} */
export function hitForbiddenDomain(relPathNormalized) {
  const p = String(relPathNormalized || "").replace(/\\/g, "/").toLowerCase()
  if (!p) return null
  if (p.includes("/.github/workflows/")) return "infra"
  const segs = p.split("/").filter(Boolean)
  for (const d of FORBIDDEN_DOMAIN_KEYS) {
    if (segs.includes(d)) return d
    if (p.includes(`/${d}/`) || p.endsWith(`/${d}`) || p.startsWith(`${d}/`)) return d
  }
  if (p.includes("secrets") || /\.env/i.test(p)) return "secrets"
  if (p.includes("migration")) return "migrations"
  return null
}

export function severityRank(sev) {
  return { critical: 4, high: 3, medium: 2, low: 1 }[String(sev)] || 2
}

/**
 * @param {{
 *   finding: any,
 *   prevFingerprintState: Record<string, any>,
 *   recurrence: boolean,
 *   autofixEnabled: boolean,
 *   agentEnabled: boolean,
 *   hasTemplatePatch: boolean,
 *   hasRequiredTests: boolean,
 *   forbiddenGlobMatch: boolean,
 *   forbiddenDomainHits: string[],
 * }} args
 */
export function computeFixRoute({
  finding,
  prevFingerprintState,
  recurrence,
  autofixEnabled,
  agentEnabled,
  hasTemplatePatch,
  hasRequiredTests,
  forbiddenDomainHits,
  forbiddenGlobMatch,
}) {
  const prev = prevFingerprintState || {}
  const declared = String(finding.rule?.targetRoute || "").toLowerCase()
  // Hard floor: rule may NEVER auto-elevate above its declared route.
  // It MAY be downgraded by safety gates below.

  const sev = finding.severity || "medium"
  const rk = severityRank(sev)

  if (prev.inProgressFix) {
    return { fixRoute: "issue_only", reason: "fix_agent_in_progress_for_fingerprint" }
  }

  if (recurrence) {
    return { fixRoute: "issue_only", reason: "recurrence_after_prior_fix" }
  }

  if (forbiddenGlobMatch) {
    return { fixRoute: "issue_only", reason: "autofix_forbidden_path_match" }
  }

  if (declared === "silent") {
    return { fixRoute: "silent", reason: "rule_declared_silent" }
  }

  if (declared === "notify_only") {
    return { fixRoute: "notify_only", reason: "rule_declared_notify_only" }
  }

  const ruleDomain = String(finding.rule?.domain || "").toLowerCase()
  if (ruleDomain && FORBIDDEN_DOMAIN_KEYS.includes(ruleDomain)) {
    return { fixRoute: "issue_only", reason: `forbidden_domain_from_rule:${ruleDomain}` }
  }

  const domainHit = forbiddenDomainHits?.length ? forbiddenDomainHits[0] : null
  if (domainHit) {
    return { fixRoute: "issue_only", reason: `forbidden_domain:${domainHit}` }
  }

  if (declared === "issue_only") {
    return { fixRoute: "issue_only", reason: "rule_declared_issue_only" }
  }

  if (rk >= 4) {
    return { fixRoute: "issue_only", reason: "severity_critical" }
  }
  if (rk >= 3) {
    return { fixRoute: "issue_only", reason: "severity_high" }
  }

  if (prev.autofixFailed) {
    const allowed = Number(finding.rule?.maxAutofixAttempts ?? 1)
    const attempts = Number(prev.autofixAttempts ?? 1)
    if (attempts >= allowed) {
      return { fixRoute: "issue_only", reason: "previous_autofix_failed_exhausted_attempts" }
    }
  }

  if (!finding.autofixAllowed) {
    if (agentEnabled && rk <= 2 && hasRequiredTests) {
      return { fixRoute: "fix_agent_request", reason: "agent_for_non_template_autofix" }
    }
    return { fixRoute: "issue_only", reason: "autofix_not_allowed_by_rules" }
  }

  // Low/medium template-capable paths
  if (hasTemplatePatch && autofixEnabled && rk <= 1) {
    if (!hasRequiredTests) return { fixRoute: "issue_only", reason: "missing_required_tests" }
    return { fixRoute: "template_patch", reason: "template_supported_low_risk" }
  }

  if (agentEnabled && rk <= 2 && hasRequiredTests && !hasTemplatePatch) {
    return { fixRoute: "fix_agent_request", reason: "no_template_patch_but_agent_enabled" }
  }

  return { fixRoute: "issue_only", reason: "no_safe_automation_path" }
}
