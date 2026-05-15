import fs from "node:fs"
import path from "node:path"
import fsp from "node:fs/promises"

function normalizeSlashes(p) {
  return String(p || "").replace(/\\/g, "/")
}

/** Simple glob matcher: supports ** (segment) and * (within segment only). */
export function minimatchLite(filePath, pattern) {
  const f = normalizeSlashes(filePath).replace(/^\.?\//, "")
  const pat = normalizeSlashes(pattern).replace(/^\.?\//, "")
  const re = globToRegex(pat)
  return re.test(f)
}

export function globToRegex(pat) {
  let rx = "^"
  for (let i = 0; i < pat.length; i++) {
    const c = pat[i]
    if (pat.slice(i, i + 2) === "**") {
      rx += ".*"
      i++
      continue
    }
    if (c === "*") {
      rx += "[^/]*"
      continue
    }
    if ("\\.^$+?(){}[]|".includes(c)) {
      rx += `\\${c}`
      continue
    }
    rx += c
  }
  rx += "$"
  return new RegExp(rx, "i")
}

function uniq(arr) {
  return [...new Set((arr || []).filter(Boolean))]
}

/**
 * Loads test-map YAML using the project's subset parser if provided (parent injects parseYamlSubset).
 */
export async function loadTestMap({ testMapPath, repoRoot, parseYamlSubset }) {
  if (!testMapPath || !parseYamlSubset) return null
  const abs = path.isAbsolute(testMapPath) ? testMapPath : path.join(repoRoot, testMapPath)
  let txt
  try {
    txt = await fsp.readFile(abs, "utf8")
  } catch {
    return null
  }
  return parseYamlSubset(txt)
}

/** @returns {{ modules: Record<string,{paths:string[]}>, reasons: string[] }} */
export function matchModules(testMapDoc, suspectedRelPaths) {
  const mods = testMapDoc?.modules || {}
  const reasons = []
  const matched = {}
  const pathsToCheck = uniq((suspectedRelPaths || []).map(normalizeSlashes)).filter(Boolean)
  for (const [name, spec] of Object.entries(mods)) {
    const pats = Array.isArray(spec?.paths) ? spec.paths : []
    for (const sp of pathsToCheck) {
      if (pats.some((pat) => minimatchLite(sp, pat))) {
        matched[name] = spec
        reasons.push(`path ${sp} matched module '${name}'`)
      }
    }
  }
  return { modules: matched, reasons }
}

/**
 * @param {{
 *   finding: any,
 *   testMapDoc: any,
 *   configPolicy: any,
 *   autofixVerificationCommands?: string[],
 *   fixRoute: string,
 * }} ctx
 */
export function selectTests({ finding, testMapDoc, configPolicy, autofixVerificationCommands, fixRoute }) {
  const suspected = uniq([stackToRelPath(finding.stackTop)].filter(Boolean))
  const mergedReasons = []
  const { modules, reasons } = matchModules(testMapDoc || {}, suspected)
  mergedReasons.push(...reasons)

  const defs = testMapDoc?.defaults || {}
  const pol = configPolicy ||
    testMapDoc?.testPolicy || {
      required: ["lint", "related-unit", "related-e2e"],
      optional: [],
      passRule: "all-required-pass",
    }

  const cmds = collectCommands(defs, modules, pol, fixRoute)

  let requiredFlat = cmds.requiredFlat
  const optionalFlat = cmds.optionalFlat

  if (!requiredFlat.length && Array.isArray(autofixVerificationCommands) && autofixVerificationCommands.length) {
    requiredFlat = uniq(autofixVerificationCommands)
    mergedReasons.push("fallback_required_from_config_autofix.verificationCommands")
  }

  const out = {
    unit: defs.unit || [],
    integration: defs.integration || [],
    e2e: defs.e2e || [],
    smoke: defs.smoke || [],
    full: defs.full || [],
    required: requiredFlat,
    optional: optionalFlat,
    reasons: uniq(mergedReasons),
    passRule: pol.passRule || "all-required-pass",
  }

  return out
}

function stackToRelPath(stackTop) {
  if (!stackTop || stackTop === "unknown-frame") return null
  const s = normalizeSlashes(stackTop)
  const head = s.split(":")[0] || ""
  return head.startsWith("/") ? head.replace(/^\/+/, "") : head
}

function collectCommands(defs, matchedModules, pol, fixRoute) {
  const requiredKeys = Array.isArray(pol.required) ? pol.required : []
  const optionalKeys = Array.isArray(pol.optional) ? pol.optional : []

  const pickKey = {
    lint: Array.isArray(defs.lint) ? [...defs.lint] : [],
    "related-unit": [],
    unit: Array.isArray(defs.unit) ? [...defs.unit] : [],
    "related-e2e": [],
    e2e: [],
    smoke: Array.isArray(defs.smoke) ? [...defs.smoke] : [],
    "full-e2e": Array.isArray(defs.full) ? [...defs.full] : [],
    "full-coverage": Array.isArray(defs.full) ? [...defs.full] : [],
  }

  const modUnits = []
  const modE2e = []
  let maxRiskRank = 0
  const riskRank = (r) =>
    ({
      critical: 4,
      high: 3,
      medium: 2,
      low: 1,
    }[String(r)] || 0)

  Object.values(matchedModules || {}).forEach((spec) => {
    if (typeof spec !== "object" || !spec) return
    if (spec.risk) maxRiskRank = Math.max(maxRiskRank, riskRank(spec.risk))
    if (Array.isArray(spec.unit)) modUnits.push(...spec.unit)
    if (Array.isArray(spec.e2e)) modE2e.push(...spec.e2e)
  })

  pickKey.unit = uniq([...(pickKey.unit || []), ...modUnits])
  pickKey.e2e = uniq([...(pickKey.e2e || []), ...modE2e])

  pickKey["related-unit"] = pickKey.unit.length ? [...pickKey.unit] : defs.unit ? [...defs.unit] : []
  pickKey["related-e2e"] = pickKey.e2e.length ? [...pickKey.e2e] : defs.smoke ? [...defs.smoke] : []

  if (fixRoute === "template_patch") {
    if (!pickKey["related-e2e"].length && pickKey.smoke.length) {
      pickKey["related-e2e"] = [...pickKey.smoke]
    }
  }

  if (fixRoute === "fix_agent_request") {
    pickKey.smoke = uniq([...(defs.smoke || []), ...(pickKey.smoke || [])])
    pickKey["related-e2e"] = uniq([...(pickKey["related-e2e"] || []), ...(pickKey.smoke || [])])
  }

  /** @type {string[]} */
  const requiredFlat = []
  /** @type {string[]} */
  const optionalFlat = []

  function expand(cat) {
    const items = uniq(pickKey[cat] || [])
    return items.filter(Boolean)
  }

  requiredKeys.forEach((k) => {
    requiredFlat.push(...expand(k))
  })
  optionalKeys.forEach((k) => optionalFlat.push(...expand(k)))

  if (fixRoute !== "ignore_or_recover" && requiredFlat.length === 0 && defs.smoke?.length) {
    requiredFlat.push(...defs.smoke)
  }

  return {
    requiredFlat: uniq(requiredFlat),
    optionalFlat: uniq(optionalFlat),
    maxRiskRank,
  }
}

function walkExists(startDir, predicate, maxFiles) {
  /** @type {string[]} */
  const out = []
  function walk(dir) {
    let entries = []
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const e of entries) {
      if (out.length >= maxFiles) return
      const fp = path.join(dir, e.name)
      if (e.isDirectory()) {
        if (e.name === "node_modules" || e.name.startsWith(".")) continue
        walk(fp)
      } else if (predicate(fp)) out.push(fp)
    }
  }
  walk(startDir)
  return out
}

/** Returns discovery report — does not claim E2E presence without evidence */
export async function discoverE2E(repoRoot, testMapDoc) {
  const g = testMapDoc?.e2eDiscovery || {}
  const patterns = uniq([
    ...(g.playwrightConfigGlobs || []),
    ...(g.cypressConfigGlobs || []),
    ...(g.specGlobs || []),
  ])
  const findings = []
  const maxHits = 200
  outer: for (const pat of patterns) {
    let hits = []
    try {
      if (pat.includes("**")) {
        hits = walkExists(
          repoRoot,
          (fp) => minimatchLite(path.relative(repoRoot, fp).replace(/\\/g, "/"), pat),
          maxHits - findings.length,
        )
      } else {
        hits = []
        let absPat = path.isAbsolute(pat) ? pat : path.join(repoRoot, pat)
        absPat = absPat.replace(/\\/g, "/")
        if (fs.existsSync(absPat))
          findings.push(normalizeSlashes(path.relative(repoRoot, absPat)))
      }
      for (const h of hits) {
        findings.push(normalizeSlashes(path.relative(repoRoot, h)))
        if (findings.length >= maxHits) break outer
      }
    } catch {
      /* ignore */
    }
  }

  let framework = null
  if (
    findings.some(
      (x) =>
        x.includes("playwright") &&
        x.toLowerCase().includes("config"),
    )
  )
    framework = "playwright"
  if (findings.some((x) => x.toLowerCase().includes("cypress"))) framework = "cypress"

  return {
    found: findings.length > 0,
    framework,
    samplePaths: uniq(findings).slice(0, 30),
    note: findings.length === 0 ? "no_matching_e2e_artifacts_under_repo" : null,
  }
}
