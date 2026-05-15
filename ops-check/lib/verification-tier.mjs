/** Required vs optional verification command execution — all required must exit 0. */

import { spawnSync } from "node:child_process"

/**
 * @param {{ required?: string[], optional?: string[] } | null} testSel
 * @param {string[]} cmdsFallback
 * @param {string} cwd
 */
export function runTieredVerification(testSel, cmdsFallback, cwd) {
  /** @type {string[]} */
  const requiredCmds =
    Array.isArray(testSel?.required) && testSel.required.length ? testSel.required : cmdsFallback

  const requiredResults = []
  const optionalResults = []
  if (!requiredCmds || requiredCmds.length === 0) {
    return {
      ok: false,
      requiredOk: false,
      tier: "required-none",
      reason: "no required verification commands (test-plan + autofix.verificationCommands empty)",
      requiredResults,
      optionalResults,
      results: requiredResults,
    }
  }

  let requiredOkOverall = true
  for (const c of requiredCmds) {
    const r = spawnSync(c, { shell: true, cwd, encoding: "utf8" })
    const row = {
      tier: "required",
      cmd: c,
      status: r.status ?? 1,
      stdout: (r.stdout || "").slice(-2000),
      stderr: (r.stderr || "").slice(-2000),
    }
    requiredResults.push(row)
    if (row.status !== 0) requiredOkOverall = false
  }

  for (const c of testSel?.optional || []) {
    const r = spawnSync(c, { shell: true, cwd, encoding: "utf8" })
    optionalResults.push({
      tier: "optional",
      cmd: c,
      status: r.status ?? 1,
      stdout: (r.stdout || "").slice(-2000),
      stderr: (r.stderr || "").slice(-2000),
    })
  }

  /** @type {string[]} */
  const optionalFails = optionalResults.filter((x) => x.status !== 0).map((x) => x.cmd)

  const combined = [...requiredResults, ...optionalResults]
  return {
    ok: requiredOkOverall,
    requiredOk: requiredOkOverall,
    blockedOptionalFails: optionalFails,
    tier: optionalFails.length ? "required-pass_optional-failed" : "required-pass",
    requiredResults,
    optionalResults,
    results: combined,
  }
}
