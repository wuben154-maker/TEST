#!/usr/bin/env node
/**
 * ops-check.mjs — 单文件运维日志巡检（设计文档 13 区块组织）
 * 无 package.json 依赖；需 Node 20+（fetch）。
 */

import crypto from "node:crypto"
import { execFileSync } from "node:child_process"
import fs from "node:fs"
import fsp from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

import { computeFixRoute, FORBIDDEN_DOMAIN_KEYS, ROUTE_VALUES } from "./lib/fix-route.mjs"
import { discoverE2E, loadTestMap, selectTests } from "./lib/test-selector.mjs"
import {
  buildFixRequest,
  forbiddenSignalsForFinding,
  validateFixRequestShape,
} from "./lib/fix-request.mjs"
import {
  deriveAllowedPathsFromSuspected,
  writeFixRequestArtifact,
  runIsolatedTemplatePatchPipeline,
  pushBranchFromWorktree,
  abortIsolatedWorktree,
  runIsolatedAgentFixPipeline,
} from "./lib/fix-runner.mjs"
import { runTieredVerification } from "./lib/verification-tier.mjs"
import { llmDiagnose, shouldAskLlm } from "./lib/llm-client.mjs"
import {
  advisorAskLlm,
  applyAdvice,
  buildAdvisorPayload,
  createAdvisorBudget,
  shouldConsultAdvisor,
  validateAdvisorOutput,
} from "./lib/route-advisor.mjs"

// ── 1. CLI and mode parsing ─────────────────────────────────────────────────

function printHelp() {
  console.log(`Usage:
  node ops-check/ops-check.mjs run [--dry-run] [--enable-advisor] [--config PATH]
  node ops-check/ops-check.mjs diagnose --since <dur> [--enable-advisor] [--config PATH]
  node ops-check/ops-check.mjs plan --since <dur> [--config PATH]
  node ops-check/ops-check.mjs validate-config [--config PATH]
  node ops-check/ops-check.mjs validate-test-map [--config PATH]

dur examples: 30m, 2h, 1d`)
}

function parseArgs(argv) {
  const args = argv.slice(2)
  const out = { cmd: null, dryRunFlag: false, since: null, config: null, enableAdvisorFlag: false }
  if (!args.length) {
    printHelp()
    process.exit(1)
  }
  out.cmd = args[0]
  if (!["run", "diagnose", "plan", "validate-config", "validate-test-map"].includes(out.cmd)) {
    printHelp()
    process.exit(1)
  }
  for (let i = 1; i < args.length; i++) {
    const a = args[i]
    if (a === "--dry-run") out.dryRunFlag = true
    else if (a === "--enable-advisor") out.enableAdvisorFlag = true
    else if (a === "--config" && args[i + 1]) out.config = args[++i]
    else if (a === "--since" && args[i + 1]) out.since = args[++i]
    else if (a === "-h" || a === "--help") {
      printHelp()
      process.exit(0)
    }
  }
  return out
}

function parseDuration(s) {
  const m = String(s).trim().match(/^(\d+)(m|h|d)$/i)
  if (!m) throw new Error(`Invalid --since value: ${s} (use e.g. 30m, 2h, 1d)`)
  const n = Number(m[1])
  const u = m[2].toLowerCase()
  const mult = u === "m" ? 60_000 : u === "h" ? 3_600_000 : 86_400_000
  return n * mult
}

// ── 2. config loading and schema validation ───────────────────────────────

function parseScalar(s) {
  s = String(s).trim()
  if (s === "true" || s === "false") return s === "true"
  if (s === "null" || s === "~") return null
  if (/^-?\d+$/.test(s)) return parseInt(s, 10)
  if (/^-?\d+\.\d+$/.test(s)) return parseFloat(s)
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1)
  }
  return s
}

export function parseYamlSubset(text) {
  const rawLines = text.split(/\r?\n/)
  const lines = []
  for (const raw of rawLines) {
    const t = raw.trim()
    if (!t || t.startsWith("#")) continue
    const indent = raw.length - raw.trimStart().length
    lines.push({ indent, raw: raw.trimEnd().slice(indent) })
  }
  let i = 0

  function parseBlock(minIndent) {
    const obj = {}
    while (i < lines.length) {
      const { indent, raw } = lines[i]
      if (indent < minIndent) break
      if (raw.startsWith("- ")) break
      const c = raw.indexOf(":")
      if (c < 0) throw new Error(`Invalid YAML line: ${raw}`)
      const key = raw.slice(0, c).trim()
      const rest = raw.slice(c + 1).trim()
      i++
      if (rest !== "") obj[key] = parseScalar(rest)
      else {
        if (i < lines.length && lines[i].indent === minIndent + 2 && lines[i].raw.startsWith("- ")) {
          obj[key] = parseArray(minIndent + 2)
        } else {
          obj[key] = parseBlock(minIndent + 2)
        }
      }
    }
    return obj
  }

  function parseArray(childIndent) {
    const arr = []
    while (i < lines.length) {
      const { indent, raw } = lines[i]
      if (indent < childIndent) break
      if (indent !== childIndent || !raw.startsWith("- ")) break
      let itemText = raw.slice(2).trim()
      i++
      if (itemText === "") {
        arr.push(parseBlock(childIndent + 2))
        continue
      }
      const c = itemText.indexOf(":")
      if (c < 0) {
        arr.push(parseScalar(itemText))
        continue
      }
      const k = itemText.slice(0, c).trim()
      const vrest = itemText.slice(c + 1).trim()
      const obj = {}
      if (vrest === "") obj[k] = parseBlock(childIndent + 2)
      else obj[k] = parseScalar(vrest)
      if (i < lines.length && lines[i].indent > childIndent) {
        Object.assign(obj, parseBlock(childIndent + 2))
      }
      arr.push(obj)
    }
    return arr
  }

  i = 0
  return parseBlock(0)
}

async function loadConfig(configPath) {
  const txt = await fsp.readFile(configPath, "utf8")
  return parseYamlSubset(txt)
}

/** Sync log group / region with `.cicd/env/<cicdEnvironment>.yaml` when using `${from-cicd-env}` or empty `logGroupNames`. */
const CICD_ENV_LOG_REF = "${from-cicd-env}"

function isMalformedEnvStylePlaceholder(s) {
  const t = String(s ?? "").trim()
  return /^\$\{[^}]+\}$/.test(t) && t !== CICD_ENV_LOG_REF
}

function throwIfInvalidCloudWatchPlaceholders(source) {
  if (source?.type !== "cloudwatch") return
  const id = source.id || "?"
  const reg = String(source.region ?? "").trim()
  if (reg && isMalformedEnvStylePlaceholder(reg)) {
    throw new Error(
      `ops-check: cloudwatch "${id}": invalid region placeholder "${source.region}". Use exactly ${CICD_ENV_LOG_REF} or a real AWS region string.`,
    )
  }
  const groups = Array.isArray(source.logGroupNames) ? source.logGroupNames : []
  for (const g of groups) {
    const gs = String(g ?? "").trim()
    if (gs && isMalformedEnvStylePlaceholder(gs)) {
      throw new Error(
        `ops-check: cloudwatch "${id}": invalid logGroupNames entry "${g}". Use exactly ${CICD_ENV_LOG_REF} or a real log group path.`,
      )
    }
  }
}

function cloudwatchNeedsCicdBinding(source) {
  if (source?.type !== "cloudwatch") return false
  if (String(source.region ?? "").trim() === CICD_ENV_LOG_REF) return true
  const groups = source.logGroupNames
  if (!Array.isArray(groups) || groups.length === 0) return true
  return groups.some((g) => g === CICD_ENV_LOG_REF)
}

function anyCloudwatchNeedsCicdBinding(cfg) {
  for (const s of cfg.logSources || []) {
    if (cloudwatchNeedsCicdBinding(s)) return true
  }
  return false
}

/**
 * Same default as CI_CD deploy-aws.yml (ec2-ssh awslogs): /ecs/{project_name}-{env_name}
 * with project_name = (repository.name or "app").
 */
async function deriveDefaultEcsLogGroupFromProject(repoRoot, cicdEnv, cicdRelPath) {
  const projectAbs = path.join(repoRoot, ".cicd", "project.yaml")
  let raw
  try {
    raw = await fsp.readFile(projectAbs, "utf8")
  } catch (e) {
    if (e?.code === "ENOENT") {
      throw new Error(
        `ops-check: ${cicdRelPath} has empty logging.cloudwatch.log_group; deploy uses /ecs/<project>-${cicdEnv} when log_group is unset.\n` +
          `Missing .cicd/project.yaml at:\n  ${projectAbs}\n` +
          `Add repository.name (same as deploy-aws.yml) or set logging.cloudwatch.log_group explicitly in ${cicdRelPath}.`,
      )
    }
    throw e
  }
  let project
  try {
    project = parseYamlSubset(raw)
  } catch (err) {
    throw new Error(`ops-check: failed to parse .cicd/project.yaml: ${err?.message || err}`)
  }
  const repo = project?.repository
  const nameRaw = repo && typeof repo === "object" && repo.name != null ? String(repo.name).trim() : ""
  const projectName = nameRaw || "app"
  return `/ecs/${projectName}-${cicdEnv}`
}

async function extractCloudWatchBindingFromCicd(data, cicdRelPath, repoRoot, cicdEnv) {
  const logging = data?.logging
  if (!logging || typeof logging !== "object") {
    throw new Error(
      `ops-check: ${cicdRelPath} must define a top-level "logging" object. Example:\n` +
        `  logging:\n    cloudwatch:\n      enabled: true\n      region: ap-southeast-1\n      log_group: /ecs/my-app-prod`,
    )
  }
  const cw = logging.cloudwatch
  if (!cw || typeof cw !== "object") {
    throw new Error(
      `ops-check: ${cicdRelPath} must define "logging.cloudwatch". Example:\n` +
        `  logging:\n    cloudwatch:\n      enabled: true\n      region: ap-southeast-1\n      log_group: /ecs/my-app-prod`,
    )
  }
  if (cw.enabled !== true) {
    throw new Error(
      `ops-check: ${cicdRelPath}: logging.cloudwatch.enabled must be true for ops-check to read logging.cloudwatch.log_group / region. CI/CD CloudWatch logging is not enabled there (enabled is not true).`,
    )
  }
  let logGroup = cw.log_group != null ? String(cw.log_group).trim() : ""
  if (!logGroup) {
    logGroup = await deriveDefaultEcsLogGroupFromProject(repoRoot, cicdEnv, cicdRelPath)
  }
  let region = cw.region != null ? String(cw.region).trim() : ""
  if (!region) {
    const aws = data?.aws
    const ar = aws && typeof aws === "object" && aws.region != null ? String(aws.region).trim() : ""
    region = ar
  }
  if (!region) {
    throw new Error(
      `ops-check: ${cicdRelPath}: set logging.cloudwatch.region or aws.region so ops-check can resolve CloudWatch region.`,
    )
  }
  return { logGroup, region }
}

/**
 * @param {any} cfg
 * @param {string} repoRoot
 * @returns {Promise<any>}
 */
export async function resolveCicdLogSourceRefs(cfg, repoRoot) {
  if (!cfg || typeof cfg !== "object" || !Array.isArray(cfg.logSources)) return cfg
  for (const s of cfg.logSources) throwIfInvalidCloudWatchPlaceholders(s)
  if (!anyCloudwatchNeedsCicdBinding(cfg)) return cfg

  const rawCicdEnv = cfg.cicdEnvironment != null ? String(cfg.cicdEnvironment).trim() : ""
  const cicdEnv = rawCicdEnv || "prod"
  const cicdRelPath = `.cicd/env/${cicdEnv}.yaml`
  const cicdAbs = path.join(repoRoot, ".cicd", "env", `${cicdEnv}.yaml`)

  let txt
  try {
    txt = await fsp.readFile(cicdAbs, "utf8")
  } catch (e) {
    if (e?.code === "ENOENT") {
      throw new Error(
        `ops-check: CloudWatch source uses ${CICD_ENV_LOG_REF} or empty logGroupNames, but CI/CD env file not found:\n  ${cicdAbs}\n` +
          `Create ${cicdRelPath} at the repository root (e.g. copy from your CI/CD template) with logging.cloudwatch.enabled: true; set log_group or rely on /ecs/<project>-${cicdEnv} via .cicd/project.yaml repository.name.`,
      )
    }
    throw e
  }

  let data
  try {
    data = parseYamlSubset(txt)
  } catch (err) {
    throw new Error(`ops-check: failed to parse ${cicdRelPath}: ${err?.message || err}`)
  }

  const binding = await extractCloudWatchBindingFromCicd(data, cicdRelPath, repoRoot, cicdEnv)
  const nextSources = cfg.logSources.map((s) => {
    if (s.type !== "cloudwatch" || !cloudwatchNeedsCicdBinding(s)) return s
    const id = s.id || "?"
    const out = { ...s }
    const groups = Array.isArray(s.logGroupNames) ? [...s.logGroupNames] : []
    const hasPh = groups.some((g) => g === CICD_ENV_LOG_REF)
    const hasExplicit = groups.some((g) => {
      if (g === CICD_ENV_LOG_REF) return false
      return String(g ?? "").trim() !== ""
    })

    if (groups.length === 0 || hasPh) {
      if (hasExplicit && hasPh) {
        throw new Error(
          `ops-check: cloudwatch "${id}": cannot mix explicit logGroupNames with ${CICD_ENV_LOG_REF}. Use either only real paths or only ${CICD_ENV_LOG_REF} or [].`,
        )
      }
      out.logGroupNames = [binding.logGroup]
    }

    if (String(out.region ?? "").trim() === CICD_ENV_LOG_REF) out.region = binding.region
    return out
  })

  return { ...cfg, logSources: nextSources }
}

function validateConfig(cfg, { forRun }) {
  const errs = []
  if (!cfg || typeof cfg !== "object") errs.push("config root must be object")
  if (!Array.isArray(cfg.logSources) || cfg.logSources.length === 0) {
    errs.push("logSources must be non-empty array")
  }
  const seen = new Set()
  for (const s of cfg.logSources || []) {
    if (!s?.id) errs.push("each log source needs id")
    else if (seen.has(s.id)) errs.push(`duplicate log source id: ${s.id}`)
    else seen.add(s.id)
    if (!s?.type) errs.push(`source ${s?.id || "?"} missing type`)
    else if (!["cloudwatch", "file", "http-json"].includes(s.type))
      errs.push(`unsupported log source type: ${s.type} (support: cloudwatch, file, http-json)`)
    if (s?.type === "cloudwatch") {
      if (!s.region) errs.push(`cloudwatch ${s.id}: region required`)
      if (!Array.isArray(s.logGroupNames) || !s.logGroupNames.length) {
        errs.push(`cloudwatch ${s.id}: logGroupNames required`)
      }
    }
    if (s?.type === "file") {
      if (!Array.isArray(s.paths) || !s.paths.length) errs.push(`file ${s.id}: paths required`)
      if (s.format && !["text", "jsonl"].includes(s.format)) {
        errs.push(`file ${s.id}: format must be text or jsonl`)
      }
      const roots = [...(s.allowedRoots || []), ...(cfg.runtime?.allowedLogRoots || [])]
      if (!roots.length) {
        errs.push(
          `file ${s.id}: set allowedRoots on source or runtime.allowedLogRoots for path constraint`,
        )
      }
    }
    if (s?.type === "http-json") {
      const hasFixedUrl = !!(s.url && String(s.url).trim())
      const hasEnvUrl = !!(s.urlEnv && String(s.urlEnv).trim())
      if (!hasFixedUrl && !hasEnvUrl) errs.push(`http-json ${s.id}: set url OR urlEnv`)
      if (hasEnvUrl && !String(process.env[s.urlEnv] || "").trim() && forRun) {
        errs.push(`http-json ${s.id}: env ${s.urlEnv} not set`)
      }
      if (s.headersEnv && typeof s.headersEnv !== "object") {
        errs.push(`http-json ${s.id}: headersEnv must be object mapping header names to ENV vars`)
      } else if (s.headersEnv) {
        for (const envName of Object.values(s.headersEnv)) {
          if (typeof envName !== "string" || !/^[A-Z0-9_]+$/.test(envName))
            errs.push(`http-json ${s.id}: header env '${envName}' must be an ENV key ref`)
          if (forRun && !process.env[String(envName)])
            errs.push(`http-json ${s.id}: header env '${envName}' not set`)
        }
      }


    }
  }
  cfg.runtime = cfg.runtime || {}
  if (cfg.runtime.dryRun === undefined) cfg.runtime.dryRun = true
  cfg.autofix = cfg.autofix || {}
  if (cfg.autofix.enabled === undefined) cfg.autofix.enabled = false
  cfg.classification = cfg.classification || {}
  if (cfg.classification.recoveryPollsToClose === undefined) cfg.classification.recoveryPollsToClose = 3
  if (cfg.classification.minOccurrencesForHigh === undefined) cfg.classification.minOccurrencesForHigh = 5
  if (cfg.classification.recurrenceEscalation === undefined) cfg.classification.recurrenceEscalation = true
  cfg.defaults = cfg.defaults || {}
  if (cfg.defaults.logLimit === undefined) cfg.defaults.logLimit = 200
  cfg.autofix.verificationCommands = cfg.autofix.verificationCommands || []
  cfg.autofix.forbiddenPaths = cfg.autofix.forbiddenPaths || []
  cfg.fixAgent = cfg.fixAgent || {}
  if (cfg.fixAgent.enabled === undefined) cfg.fixAgent.enabled = false
  if (cfg.testMapPath !== undefined && cfg.testMapPath !== null && typeof cfg.testMapPath !== "string") {
    errs.push("testMapPath must be a string relative path or omitted")
  }
  if (cfg.autofix.maxLlmCallsPerRun === undefined) cfg.autofix.maxLlmCallsPerRun = 3
  if (cfg.autofix.maxLlmCallsPerDay === undefined) cfg.autofix.maxLlmCallsPerDay = 100
  if (cfg.autofix.maxIssueActionsPerRun === undefined) cfg.autofix.maxIssueActionsPerRun = 20
  if (cfg.autofix.maxFeishuPerRun === undefined) cfg.autofix.maxFeishuPerRun = 20
  if (cfg.autofix.maxGithubRetries === undefined) cfg.autofix.maxGithubRetries = 2
  if (cfg.autofix.maxPrsPerRun === undefined) cfg.autofix.maxPrsPerRun = 1
  cfg.issues = cfg.issues || {}
  cfg.issues.labels = cfg.issues.labels || ["ops-check", "automated"]
  cfg.notifications = cfg.notifications || {}
  cfg.notifications.feishuWebhookEnv = cfg.notifications.feishuWebhookEnv || "FEISHU_WEBHOOK_URL"
  cfg.notifications.escalationWebhookEnv = cfg.notifications.escalationWebhookEnv || "FEISHU_ESCALATION_WEBHOOK_URL"
  if (cfg.notifications.escalatePrAfterMinutes === undefined) cfg.notifications.escalatePrAfterMinutes = 60

  cfg.routingAdvisor = cfg.routingAdvisor || {}
  if (cfg.routingAdvisor.enabled === undefined) cfg.routingAdvisor.enabled = false
  if (cfg.routingAdvisor.minConfidence === undefined) cfg.routingAdvisor.minConfidence = 0.6
  if (cfg.routingAdvisor.maxCallsPerRun === undefined) cfg.routingAdvisor.maxCallsPerRun = 5

  if (cfg.runtime.stateFile) {
    const sf = path.resolve(process.cwd(), cfg.runtime.stateFile)
    const rr = process.cwd()
    if (!sf.startsWith(rr + path.sep) && sf !== rr) {
      errs.push("runtime.stateFile must be inside repository workspace")
    }
  }

  return errs
}

// ── 3b. http-json fetcher (generic webhook / log-export API surface) ────────

async function fetchHttpJsonLogs({ since, until, cursor, limit, source, sharedConfig }) {
  void cursor
  void limit
  const svc = source.service || "unknown-service"
  const messageField = source.messageField || "message"
  const timeField = source.timestampField || "timestamp"

  let urlRaw = source.url ? String(source.url) : ""
  if (source.urlEnv) urlRaw = String(process.env[String(source.urlEnv)] || "").trim()

  const urlBase = urlRaw.trim()
  if (!urlBase) throw new Error(`http-json ${source.id}: missing url`)

  /** @type {Record<string,string>} */
  const headers = { Accept: "application/json" }
  if (source.headersEnv && typeof source.headersEnv === "object") {
    for (const [hk, envName] of Object.entries(source.headersEnv)) {
      const v = process.env[String(envName)]
      if (!v) throw new Error(`http-json ${source.id}: env '${envName}' missing for header ${hk}`)
      headers[String(hk)] = v
    }
  }

  const method = String(source.method || "GET").toUpperCase()
  const untilMs = until ? until.getTime() : Date.now()
  const winMin = source.queryWindowMinutes ?? sharedConfig.defaults?.queryWindowMinutes ?? 30
  const sinceMs = since != null ? since.getTime() : untilMs - winMin * 60_000

  let urlFinal = urlBase
  try {
    const u = new URL(urlFinal)
    if ((source.attachTimeQuery === undefined || source.attachTimeQuery) && method === "GET") {
      u.searchParams.set("since_ms", String(sinceMs))
      u.searchParams.set("until_ms", String(untilMs))
    }
    urlFinal = u.toString()
  } catch {
    /* ignore */
  }

  const opts = { method, headers }
  if (method !== "GET" && method !== "HEAD") {
    opts.body = JSON.stringify({
      ...(source.bodyJsonDefaults && typeof source.bodyJsonDefaults === "object"
        ? source.bodyJsonDefaults
        : {}),
      since_ms: sinceMs,
      until_ms: untilMs,
    })
    if (!opts.headers["Content-Type"]) opts.headers["Content-Type"] = "application/json"
  }

  const res = await fetch(urlFinal, opts)
  if (!res.ok) throw new Error(`http-json fetch failed (${res.status})`)
  /** @type {any} */
  let data
  try {
    data = await res.json()
  } catch {
    throw new Error("http-json: response not JSON")
  }

  /** @type {any[]} */
  let rows = []
  if (Array.isArray(data)) rows = data
  else if (data?.items && Array.isArray(data.items)) rows = data.items
  else if (data?.events && Array.isArray(data.events)) rows = data.events

  const cap = Math.min(rows?.length ?? 0, sharedConfig.defaults?.logLimit ?? 200)
  const entries = []
  for (const row of rows.slice(-cap)) {
    if (!row || typeof row !== "object") continue
    const tsRaw = row[timeField]
    const ts = tsRaw != null ? new Date(tsRaw) : new Date(untilMs)
    const svcField = source.serviceField || "service"
    const srv = row[svcField] != null ? String(row[svcField]) : svc
    const strm = row[source.streamField || "stream"]
    const msg = row[messageField] != null ? String(row[messageField]) : JSON.stringify(row)
    entries.push({
      timestamp: ts,
      message: msg,
      service: srv,
      source: source.id,
      stream: strm ? String(strm) : "http-json",
      raw: row,
    })
  }

  const filtered =
    since != null ? entries.filter((e) => e.timestamp >= since && (!until || e.timestamp <= until)) : entries

  return { entries: filtered, nextCursor: null }
}

// ── 3. fetcher registry ────────────────────────────────────────────────────

function buildFetcherRegistry() {
  return {
    cloudwatch: fetchCloudWatchLogs,
    file: fetchFileLogs,
    "http-json": fetchHttpJsonLogs,
  }
}

// ── 4. CloudWatch fetcher ─────────────────────────────────────────────────

async function fetchCloudWatchLogs({ since, until, cursor, limit, source, sharedConfig }) {
  const region = source.region
  const groups = source.logGroupNames || []
  const max = limit ?? sharedConfig.defaults?.logLimit ?? 200
  const winMin = source.queryWindowMinutes ?? 10
  const untilMs = until ? until.getTime() : Date.now()
  const sinceMs = since ? since.getTime() : untilMs - winMin * 60_000
  const entries = []
  let nextCursor = cursor?.token ?? null

  for (const group of groups) {
    const args = [
      "logs",
      "filter-log-events",
      "--region",
      region,
      "--log-group-name",
      group,
      "--start-time",
      String(sinceMs),
      "--end-time",
      String(untilMs),
      "--limit",
      String(Math.min(max, 10000)),
      "--output",
      "json",
    ]
    if (source.filterPattern) {
      args.push("--filter-pattern", source.filterPattern)
    }
    if (nextCursor) args.push("--starting-token", String(nextCursor))

    /** @type {string} */
    let out
    try {
      out = execFileSync("aws", args, {
        encoding: "utf8",
        env: process.env,
        stdio: ["ignore", "pipe", "pipe"],
        maxBuffer: 20 * 1024 * 1024,
      })
    } catch (e) {
      const msg = e.stderr?.toString?.() || e.message
      throw new Error(`CloudWatch aws cli failed for ${group}: ${msg}`)
    }
    let data
    try {
      data = JSON.parse(out)
    } catch {
      throw new Error(`CloudWatch JSON parse failed for ${group}`)
    }
    for (const e of data.events || []) {
      let svc = source.service || "unknown-service"
      let msg = e.message || ""
      if (source.serviceField) {
        try {
          const j = JSON.parse(msg)
          if (j && typeof j === "object" && j[source.serviceField]) svc = String(j[source.serviceField])
        } catch {
          /* keep */
        }
      }
      entries.push({
        timestamp: new Date(e.timestamp),
        message: msg,
        service: svc,
        source: source.id,
        stream: e.logStreamName || "",
        raw: e,
      })
    }
    if (data.nextToken) nextCursor = data.nextToken
  }
  return { entries, nextCursor: nextCursor ? { token: nextCursor } : null }
}

// ── 5. file fetcher ────────────────────────────────────────────────────────

const SENSITIVE_PATH_REJECT = [
  /\.env/i,
  /secrets/i,
  /id_rsa/i,
  /\.pem$/i,
  /\.key$/i,
  /credential/i,
  /github.*token/i,
]

function isSensitivePath(p) {
  const n = p.replace(/\\/g, "/")
  if (n.includes(".env")) return true
  if (/^\/etc\/shadow$/i.test(n)) return true
  return SENSITIVE_PATH_REJECT.some((re) => {
    try {
      return re.test(n)
    } catch {
      return false
    }
  })
}

function collectAllowedRoots(source, cfg) {
  const roots = []
  if (Array.isArray(source.allowedRoots)) roots.push(...source.allowedRoots)
  if (Array.isArray(cfg.runtime?.allowedLogRoots)) roots.push(...cfg.runtime.allowedLogRoots)
  return [...new Set(roots.map((r) => path.resolve(r)))]
}

function pathUnderRoots(resolved, roots) {
  if (!roots.length) return true
  return roots.some((r) => resolved === r || resolved.startsWith(r + path.sep))
}

async function expandGlobPattern(pattern) {
  if (!pattern.includes("*") && !pattern.includes("?")) return [path.resolve(pattern)]
  const dir = path.dirname(pattern.split("*")[0])
  const base = path.basename(pattern)
  let starIdx = base.indexOf("*")
  if (starIdx < 0) starIdx = base.length
  const prefix = base.slice(0, starIdx).replace(/\*.*$/, "")
  let rd = dir
  try {
    await fsp.access(rd)
  } catch {
    return []
  }
  const entries = await fsp.readdir(rd, { withFileTypes: true })
  const out = []
  const rx = globToRegex(path.basename(pattern))
  for (const ent of entries) {
    if (!ent.isFile()) continue
    if (rx.test(ent.name)) out.push(path.join(rd, ent.name))
  }
  return out
}

function globToRegex(g) {
  const esc = g.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".")
  return new RegExp(`^${esc}$`, "i")
}

async function fetchFileLogs({ since, until, cursor, limit, source, sharedConfig }) {
  const enc = source.encoding || "utf8"
  const fmt = source.format || "text"
  const max = limit ?? sharedConfig.defaults?.logLimit ?? 200
  const roots = collectAllowedRoots(source, sharedConfig)
  const entries = []
  const paths = []
  for (const pat of source.paths || []) {
    paths.push(...(await expandGlobPattern(pat)))
  }
  let used = 0
  for (const fp of paths) {
    const resolved = path.resolve(fp)
    if (isSensitivePath(resolved)) throw new Error(`Rejected sensitive path: ${resolved}`)
    if (!pathUnderRoots(resolved, roots)) {
      throw new Error(`Path not under allowed roots: ${resolved}`)
    }
    let st
    try {
      st = await fsp.stat(resolved)
    } catch {
      continue
    }
    const text = await fsp.readFile(resolved, enc)
    if (fmt === "text") {
      const lines = text.split(/\r?\n/).filter(Boolean)
      const mtime = st.mtime
      for (const line of lines.slice(-max)) {
        used++
        if (used > max) break
        entries.push({
          timestamp: mtime,
          message: line,
          service: source.service || "unknown-service",
          source: source.id,
          stream: path.basename(resolved),
          raw: { path: resolved, timestampInferred: true },
        })
      }
    } else if (fmt === "jsonl") {
      const lines = text.split(/\r?\n/).filter(Boolean)
      for (const line of lines.slice(-max)) {
        used++
        if (used > max) break
        let j
        try {
          j = JSON.parse(line)
        } catch {
          continue
        }
        const tsField = source.timestampField || "timestamp"
        const msgField = source.messageField || "message"
        const svcField = source.serviceField
        let ts = j[tsField] ? new Date(j[tsField]) : st.mtime
        let inferred = !j[tsField]
        let svc = source.service || "unknown-service"
        if (svcField && j[svcField]) svc = String(j[svcField])
        entries.push({
          timestamp: ts,
          message: String(j[msgField] ?? line),
          service: svc,
          source: source.id,
          stream: path.basename(resolved),
          raw: { path: resolved, timestampInferred: inferred, obj: j },
        })
      }
    }
  }
  if (since) {
    return {
      entries: entries.filter((e) => e.timestamp >= since && (!until || e.timestamp <= until)),
      nextCursor: null,
    }
  }
  return { entries, nextCursor: null }
}

// ── 6. entry normalization and merge ────────────────────────────────────────

function normalizeAndSortEntries(all) {
  const sorted = [...all].sort((a, b) => a.timestamp - b.timestamp)
  return sorted
}

// ── 7. redaction ───────────────────────────────────────────────────────────

function redactText(s) {
  if (!s) return s
  let out = s
  out = out.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, "[REDACTED_EMAIL]")
  out = out.replace(/\bBearer\s+[A-Za-z0-9._\-]+\b/gi, "Bearer [REDACTED]")
  out = out.replace(/\bsk-[A-Za-z0-9]{20,}\b/gi, "[REDACTED_SECRET]")
  out = out.replace(/\beyJ[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b/g, "[REDACTED_JWT]")
  out = out.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "[REDACTED_UUID]")
  out = out.replace(/\b\d{1,3}(?:\.\d{1,3}){3}\b/g, "[REDACTED_IP]")
  return out
}

// ── 8. rule matching and LLM fallback ───────────────────────────────────────

function loadRulesDoc(raw) {
  const doc = parseYamlSubset(raw)
  return Array.isArray(doc.rules) ? doc.rules : []
}

const ALLOWED_RULE_SEVERITY = new Set(["critical", "high", "medium", "low"])
const ALLOWED_TARGET_ROUTE = new Set(ROUTE_VALUES)

function validateRules(rules) {
  const errs = []
  const names = new Set()
  for (const r of rules) {
    if (!r.name) errs.push("rule missing name")
    else if (names.has(r.name)) errs.push(`duplicate rule name: ${r.name}`)
    else names.add(r.name)
    if (!r.pattern) errs.push(`${r.name || "?"}: pattern required`)
    if (r.severity && !ALLOWED_RULE_SEVERITY.has(String(r.severity)))
      errs.push(`${r.name}: invalid severity ${r.severity}`)
    if (r.targetRoute && !ALLOWED_TARGET_ROUTE.has(String(r.targetRoute).toLowerCase()))
      errs.push(`${r.name}: invalid targetRoute ${r.targetRoute}`)
    try {
      new RegExp(r.pattern, "i")
    } catch (e) {
      errs.push(`${r.name}: bad pattern: ${e.message}`)
    }
    if (r.excludePattern) {
      try {
        new RegExp(r.excludePattern, "i")
      } catch (e) {
        errs.push(`${r.name}: bad excludePattern: ${e.message}`)
      }
    }
  }
  return errs
}

function pathGlobToRegex(glob) {
  const esc = String(glob).replace(/[.+^${}()|[\]\\]/g, "\\$&")
  const pat = esc.replace(/\*\*/g, "::DSTAR::").replace(/\*/g, "[^/]*").replace(/::DSTAR::/g, ".*")
  return new RegExp("^" + pat + "$", "i")
}

function stackPathOnly(stackTop) {
  const s = String(stackTop || "")
  const m = s.match(/^(.+):(\d+)$/)
  return m ? m[1] : s
}

export function matchRules(message, rules, opts) {
  const stackTop = opts?.stackTop || ""
  const pathForGlob = String(stackPathOnly(stackTop)).replace(/\\/g, "/")
  const hits = []
  for (const r of rules) {
    if (!r.pattern) continue
    try {
      const re = new RegExp(r.pattern, "i")
      if (!re.test(message)) continue
      if (r.excludePattern) {
        try {
          const ex = new RegExp(r.excludePattern, "i")
          if (ex.test(message)) continue
        } catch {
          /* skip bad excludePattern */
        }
      }
      if (Array.isArray(r.excludePath) && r.excludePath.length && pathForGlob) {
        const hitGlob = r.excludePath.some((g) => {
          try {
            const glob = typeof g === "string" ? g : g?.value ?? g
            return pathGlobToRegex(glob).test(pathForGlob)
          } catch {
            return false
          }
        })
        if (hitGlob) continue
      }
      hits.push(r)
    } catch {
      /* skip bad pattern */
    }
  }
  return hits
}

function parseShortDuration(s) {
  const m = String(s || "")
    .trim()
    .match(/^(\d+)(s|m|h)$/i)
  if (!m) return 0
  const n = Number(m[1])
  const u = m[2].toLowerCase()
  if (u === "s") return n * 1000
  if (u === "m") return n * 60_000
  return n * 3600_000
}

function extractStackTop(message) {
  const lines = message.split(/\r?\n/)
  for (const ln of lines) {
    const m = ln.match(/File "([^"]+)", line (\d+)/)
    if (m) return `${m[1]}:${m[2]}`
    const m2 = ln.match(/\(([^():]+\.(?:jsx?|tsx?|py|go|rs)):(\d+)(?::\d+)?\)/)
    if (m2) return `${m2[1]}:${m2[2]}`
    const m3 = ln.match(/at\s+.+\s+\(([^:]+):(\d+):(\d+)\)/)
    if (m3) return `${m3[1]}:${m3[2]}`
  }
  return "unknown-frame"
}

function normalizeMessageTemplate(msg) {
  let s = redactText(msg)
  s = s.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "<UUID>")
  s = s.replace(/\breq(?:uest)?[_-]?id[:=]\s*\S+/gi, "req_id:<ID>")
  s = s.replace(/\btrace[_-]?id[:=]\s*\S+/gi, "trace:<ID>")
  s = s.replace(/\buser[_-]?id[:=]\s*\S+/gi, "user:<ID>")
  s = s.slice(0, 500)
  return s
}

// ── 9. fingerprint and state handling ───────────────────────────────────────

function utcDayKey(ms) {
  return new Date(ms).toISOString().slice(0, 10)
}

export function fingerprintFrom({ service, errorType, msgTpl, stackTop, environment }) {
  const h = crypto.createHash("sha256")
  h.update([service, errorType, msgTpl, stackTop, environment].join("|"))
  return h.digest("hex")
}

export async function readState(stateFile) {
  try {
    const t = await fsp.readFile(stateFile, "utf8")
    const o = JSON.parse(t)
    o.cursors = o.cursors || {}
    o.fingerprints = o.fingerprints || {}
    o.llmVerdicts = o.llmVerdicts && typeof o.llmVerdicts === "object" ? o.llmVerdicts : {}
    o.advisorVerdicts =
      o.advisorVerdicts && typeof o.advisorVerdicts === "object" ? o.advisorVerdicts : {}
    if (!o.llmDailyUsage || typeof o.llmDailyUsage !== "object") o.llmDailyUsage = { date: "", count: 0 }
    return o
  } catch {
    return {
      cursors: {},
      fingerprints: {},
      llmVerdicts: {},
      advisorVerdicts: {},
      llmDailyUsage: { date: "", count: 0 },
    }
  }
}

export async function writeState(stateFile, state, effects) {
  if (!effects.canWriteState) return
  const out = {
    ...state,
    llmVerdicts: state.llmVerdicts && typeof state.llmVerdicts === "object" ? state.llmVerdicts : {},
    advisorVerdicts:
      state.advisorVerdicts && typeof state.advisorVerdicts === "object" ? state.advisorVerdicts : {},
    llmDailyUsage:
      state.llmDailyUsage && typeof state.llmDailyUsage === "object"
        ? state.llmDailyUsage
        : { date: "", count: 0 },
  }
  await fsp.mkdir(path.dirname(stateFile), { recursive: true })
  await fsp.writeFile(stateFile, JSON.stringify(out, null, 2), "utf8")
}

// ── 10. action planning ───────────────────────────────────────────────────

function severityRank(s) {
  return { critical: 4, high: 3, medium: 2, low: 1 }[s] || 2
}

function mergeSeverity(a, b) {
  return severityRank(a) >= severityRank(b) ? a : b
}

export async function analyzePipeline({
  cfg,
  entries,
  rules,
  environment,
  project,
  diagnoseMode,
  usedLlm,
  prevLlmVerdicts = {},
  nowMs = Date.now(),
  llmDailyUsageInitial = { date: "", count: 0 },
}) {
  const ttlMs = parseShortDuration(String(cfg.autofix.llmVerdictTtl ?? "24h")) || 86_400_000
  const maxDay = cfg.autofix.maxLlmCallsPerDay ?? 100
  const dailyUsage = { ...llmDailyUsageInitial }
  const dk = utcDayKey(nowMs)
  if (dailyUsage.date !== dk) {
    dailyUsage.date = dk
    dailyUsage.count = 0
  }

  const llmCacheThisRun = new Map()
  const llmVerdictsDelta = {}
  let llmHttpCalls = 0
  let cacheHitsRun = 0
  let cacheHitsState = 0
  let heuristicSkips = 0
  let exhaustedFlag = false
  const model = process.env.OPENAI_MODEL || "deepseek-ai/DeepSeek-V4-Pro"

  const findings = new Map()
  const entryRows = []
  for (const ent of entries) {
    const msg = redactText(ent.message)
    const stackTopEarly = extractStackTop(ent.message)
    const hits = matchRules(msg, rules, { stackTop: stackTopEarly })
    let severity = "medium"
    let autofix = false
    let ruleName = null
    if (hits.length) {
      const hs = hits.map((h) => h.severity || "medium")
      severity = hs.reduce(mergeSeverity)
      autofix = hits.some((h) => h.autofix === true)
      ruleName = hits.map((h) => h.name).join(",")
    } else {
      const stackTop = extractStackTop(ent.message)
      const msgTpl = normalizeMessageTemplate(msg)
      const llmFp = fingerprintFrom({
        service: ent.service,
        errorType: "unknown",
        msgTpl,
        stackTop,
        environment,
      })

      let diag = null

      try {
        const skip = shouldAskLlm(msg)
        if (skip) {
          diag = { severity: skip.severity, autofix: skip.autofix, rationale: skip.source || "" }
          ruleName = "heuristic-skip"
          heuristicSkips++
        }
      } catch {
        /* fail-open: proceed toward LLM */
      }

      if (!diag) {
        const cachedState = prevLlmVerdicts[llmFp]
        if (
          cachedState &&
          typeof cachedState.ts === "number" &&
          cachedState.ts + (cachedState.ttlMs ?? ttlMs) > nowMs &&
          cachedState.model === model
        ) {
          diag = {
            severity: cachedState.severity || "medium",
            autofix: !!cachedState.autofix,
            rationale: "state-cache",
          }
          ruleName = "llm-fallback(state-cache)"
          cacheHitsState++
        } else if (llmCacheThisRun.has(llmFp)) {
          diag = { ...llmCacheThisRun.get(llmFp) }
          ruleName = "llm-fallback(cached)"
          cacheHitsRun++
        } else {
          const summaryForLlm = normalizeMessageTemplate(msg)
          const maxRun = cfg.autofix.maxLlmCallsPerRun ?? 3
          const runBudgetFull = usedLlm.count >= maxRun
          const dayBudgetFull = dailyUsage.count >= maxDay
          if (runBudgetFull || dayBudgetFull) {
            exhaustedFlag = true
            diag = {
              severity: "medium",
              autofix: false,
              rationale: runBudgetFull ? "LLM budget exhausted" : "LLM daily budget exhausted",
            }
            ruleName = "llm-fallback"
          } else {
            const raw = await llmDiagnose(
              {
                cfg,
                summary: summaryForLlm,
                stackTop,
                service: ent.service,
              },
              usedLlm,
              { dailyUsage, maxPerDay: maxDay, nowMs },
            )
            if (String(raw.rationale || "").includes("budget exhausted")) exhaustedFlag = true
            diag = {
              severity: raw.severity || "medium",
              autofix: !!raw.autofix,
              rationale: raw.rationale || "",
            }
            llmCacheThisRun.set(llmFp, diag)
            ruleName = "llm-fallback"
            if (raw._llmOk) {
              llmHttpCalls++
              llmVerdictsDelta[llmFp] = {
                severity: diag.severity || "medium",
                autofix: !!diag.autofix,
                ts: nowMs,
                ttlMs,
                model,
              }
              dailyUsage.count++
            }
          }
        }
      }

      severity = diag.severity
      autofix = diag.autofix && cfg.autofix.enabled
      if (!cfg.autofix.enabled) autofix = false
    }
    const stackTop = extractStackTop(ent.message)
    const msgTpl = normalizeMessageTemplate(msg)
    const errType = hits[0]?.name || "unknown"
    const fp = fingerprintFrom({
      service: ent.service,
      errorType: errType,
      msgTpl,
      stackTop,
      environment,
    })
    entryRows.push({
      source: ent.source,
      service: ent.service,
      stream: ent.stream,
      timestamp: ent.timestamp.toISOString(),
      timestampInferred: !!(ent.raw && ent.raw.timestampInferred),
      excerpt: msg.slice(0, 160),
      ruleName,
      fingerprint: fp,
    })
    const cur = findings.get(fp) || {
      fingerprint: fp,
      service: ent.service,
      severity,
      ruleName,
      messages: [],
      sources: new Set(),
      autofixAllowed: false,
      stackTop,
      msgTpl,
      rule: null,
      occurrenceTimes: [],
    }
    cur.messages.push(msg.slice(0, 2000))
    cur.sources.add(ent.source)
    cur.occurrenceTimes.push(typeof ent.timestamp?.getTime === "function" ? ent.timestamp.getTime() : Date.now())
    if (hits.length && !cur.rule) cur.rule = hits[0]
    cur.severity = mergeSeverity(cur.severity, severity)
    if (hits.length && hits.some((h) => h.autofix === true)) cur.autofixAllowed = true
    if (cur.sources.size > 1 && severityRank(cur.severity) < 3) cur.severity = "high"
    const minOcc = (cfg.classification.minOccurrencesForHigh ?? 5) || 5
    if (cur.messages.length >= minOcc && severityRank(cur.severity) < 3) cur.severity = "high"
    if (!hits.length) cur.autofixAllowed = false
    findings.set(fp, cur)
  }

  const maxRunCap = cfg.autofix.maxLlmCallsPerRun ?? 3
  const llmStats = {
    calls: llmHttpCalls,
    cacheHitsRun,
    cacheHitsState,
    heuristicSkips,
    exhausted: exhaustedFlag,
    budgetRemainingRun: Math.max(0, maxRunCap - usedLlm.count),
    budgetRemainingDay: Math.max(0, maxDay - dailyUsage.count),
    model,
  }

  return {
    findings: [...findings.values()],
    entryRows,
    llmStats,
    llmVerdictsDelta,
    llmDailyUsageNext: dailyUsage,
  }
}

function plannedActionLabel(fp, plan) {
  for (const p of plan.agentFixes || []) {
    if (p.finding.fingerprint === fp) return "agent_fix_pr"
  }
  for (const p of plan.prs) {
    if (p.finding.fingerprint === fp) return "autofix_pr"
  }
  for (const is of plan.issues) {
    if (is.fingerprint === fp) {
      if (is.kind === "close") return "close_issue"
      return is.kind || "issue"
    }
    if (is.finding?.fingerprint === fp) return is.kind || "issue"
  }
  return "none"
}

function printDiagnosticSummary({ cfg, entryRows, plan, enrichment }) {
  const enr = enrichment || {}
  for (const row of entryRows) {
    const ef = enr[row.fingerprint] || {}
    const action = plannedActionLabel(row.fingerprint, plan)
    const line = [
      `source=${row.source}`,
      `service=${row.service}`,
      `stream=${redactText(row.stream)}`,
      `timestamp=${row.timestamp}`,
      `timestampInferred=${row.timestampInferred}`,
      `excerpt=${redactText(row.excerpt)}`,
      `rule=${row.ruleName}`,
      `fingerprint=${row.fingerprint}`,
      `plannedAction=${action}`,
      `fixRoute=${ef.fixRoute || "n/a"}`,
      `testRequiredCount=${Array.isArray(ef.testPlan?.required) ? ef.testPlan.required.length : 0}`,
    ].join(" | ")
    console.log(line)
  }
}

function formatAdvisorFooterLine(adv) {
  if (!adv || typeof adv !== "object") {
    return "\nadvisor: consulted=false veto=n/a code=n/a conf=n/a model=n/a\n"
  }
  const consulted = adv.consulted === true ? "true" : "false"
  const veto = adv.veto === true ? "true" : adv.veto === false ? "false" : "n/a"
  const code = adv.code != null ? String(adv.code).replace(/\s+/g, "_") : "n/a"
  const conf = typeof adv.confidence === "number" ? adv.confidence.toFixed(2) : "n/a"
  const model = adv.model != null ? String(adv.model).replace(/\s+/g, "_") : "n/a"
  return `\nadvisor: consulted=${consulted} veto=${veto} code=${code} conf=${conf} model=${model}\n`
}

function applyAdvisorBatchSync({ cfg, enrichment, pendingAdvisor, verdicts, stats }) {
  const model = process.env.OPENAI_MODEL || "deepseek-ai/DeepSeek-V4-Pro"
  for (const p of pendingAdvisor) {
    const en = enrichment[p.fingerprint]
    if (!en) continue
    const raw = verdicts.has(p.fingerprint) ? verdicts.get(p.fingerprint) : undefined
    let adviceObj = null
    if (raw !== undefined && raw !== null && typeof raw === "object") {
      const v = validateAdvisorOutput(raw)
      adviceObj = v.ok ? v.value : null
    } else if (raw === null) {
      adviceObj = null
    }
    const out = applyAdvice({ proposed: p.proposed, advice: adviceObj, cfg })
    stats.consulted++
    if (out.advisorPassed) {
      stats.passed++
      en.fixRoute = out.fixRoute
      en.routingReason = out.routingReason
      en.advisor = {
        consulted: true,
        veto: false,
        code: adviceObj?.code ?? "ok",
        confidence: adviceObj?.confidence,
        model,
      }
    } else {
      if (String(out.reason || "").startsWith("llm_veto:")) stats.vetoed++
      else if (String(out.reason || "").includes("llm_low_confidence")) stats.lowConfidence++
      else stats.errors++
      en.fixRoute = out.fixRoute
      en.routingReason = out.reason
      en.advisor = {
        consulted: true,
        veto: String(out.reason || "").startsWith("llm_veto:"),
        code: adviceObj?.code ?? "fail_closed",
        confidence: adviceObj?.confidence,
        model,
      }
      en.fixRequest = buildFixRequest({
        finding: p.finding,
        cfg,
        fixRoute: en.fixRoute,
        testPlan: en.testPlan,
        allowedEditPaths: p.fixRequest.allowedEditPaths,
        forbiddenEditPaths: p.fixRequest.forbiddenEditPaths,
        forbiddenDomainsTriggered: [...(p.fixRequest.forbiddenDomains || [])],
        routingReason: en.routingReason,
      })
      const shapeErrs = validateFixRequestShape(en.fixRequest)
      en.fixRequestValidated = shapeErrs.length === 0
      en.fixRequestShapeErrors = shapeErrs
    }
  }
}

async function consultAdvisorsAndReroute({
  cfg,
  findings,
  enrichment,
  pendingAdvisor,
  runFlags,
  state,
  nowMs = Date.now(),
  llmDailyUsage,
}) {
  const emptyStats = { consulted: 0, vetoed: 0, passed: 0, lowConfidence: 0, errors: 0 }
  if (!pendingAdvisor.length) return { stats: emptyStats, verdicts: new Map(), advisorVerdictsDelta: {} }
  if (!cfg.routingAdvisor?.enabled || runFlags.advisorAllowed !== true) return { stats: emptyStats, verdicts: new Map(), advisorVerdictsDelta: {} }

  const budget = createAdvisorBudget(cfg)
  const maxDay = cfg.autofix.maxLlmCallsPerDay ?? 100
  const verdicts = new Map()
  const model = process.env.OPENAI_MODEL || "deepseek-ai/DeepSeek-V4-Pro"
  const ttlMs = parseShortDuration(String(cfg.routingAdvisor.verdictTtl ?? "6h")) || 21_600_000
  const advisorVerdictsDelta = {}

  for (const p of pendingAdvisor) {
    const cached = state?.advisorVerdicts?.[p.fingerprint]
    if (
      cached &&
      typeof cached.ts === "number" &&
      cached.ts + (cached.ttlMs ?? ttlMs) > nowMs &&
      cached.model === model &&
      cached.candidateRoute === p.proposed.fixRoute
    ) {
      verdicts.set(p.fingerprint, {
        veto: !!cached.veto,
        code: String(cached.code || "fail_closed"),
        confidence: typeof cached.confidence === "number" ? cached.confidence : 0,
        rationale: "",
      })
      continue
    }

    const payload = buildAdvisorPayload({
      finding: p.finding,
      candidate: p.proposed.fixRoute,
      fixRequest: p.fixRequest,
    })
    const advice = await advisorAskLlm({
      cfg,
      payload,
      budget,
      dailyUsage: llmDailyUsage,
      maxPerDay: maxDay,
      nowMs,
    })
    verdicts.set(p.fingerprint, advice)
    if (advice && validateAdvisorOutput(advice).ok) {
      advisorVerdictsDelta[p.fingerprint] = {
        veto: !!advice.veto,
        code: String(advice.code),
        confidence: advice.confidence,
        model,
        candidateRoute: p.proposed.fixRoute,
        ts: nowMs,
        ttlMs,
      }
    }
  }

  const stats = { consulted: 0, vetoed: 0, passed: 0, lowConfidence: 0, errors: 0 }
  applyAdvisorBatchSync({ cfg, enrichment, pendingAdvisor, verdicts, stats })
  return { stats, verdicts, advisorVerdictsDelta }
}

function peekTemplatePatch(finding, repoRoot) {
  return !!tryBuildAutofixPatch({ finding, repoRoot })
}

function buildFingerprintEnrichment({ cfg, findings, state, testMapDoc, repoRoot, runFlags }) {
  const enrichment = {}
  /** @type {any[]} */
  const pendingAdvisor = []
  const rf = runFlags || { advisorAllowed: false }
  const agentEnabled = cfg.fixAgent?.enabled === true
  const autofixEnabled = cfg.autofix.enabled === true
  for (const f of findings) {
    const prev = state.fingerprints[f.fingerprint] || {}
    const recurrence = !!(prev.mergedFix && cfg.classification.recurrenceEscalation)
    const pickFixRouteGuess =
      severityRank(f.severity) <= 2 && (f.autofixAllowed || agentEnabled || autofixEnabled)
        ? "fix_agent_request"
        : "issue_only"

    const testSel = selectTests({
      finding: f,
      testMapDoc,
      configPolicy: cfg.testPolicy ?? null,
      autofixVerificationCommands: cfg.autofix.verificationCommands,
      fixRoute: pickFixRouteGuess === "issue_only" ? "issue_only" : "fix_agent_request",
    })

    const hasTpl = peekTemplatePatch(f, repoRoot)
    const signals = forbiddenSignalsForFinding(f, cfg, repoRoot)
    const domainHits = (signals.hits || []).filter((h) => [...FORBIDDEN_DOMAIN_KEYS].includes(h))
    const forbiddenGlob = (signals.hits || []).includes("forbidden_glob_match")

    const hasReqTests = Array.isArray(testSel.required) && testSel.required.length > 0

    const route = computeFixRoute({
      finding: f,
      prevFingerprintState: prev,
      recurrence,
      autofixEnabled,
      agentEnabled,
      hasTemplatePatch: hasTpl,
      hasRequiredTests: hasReqTests,
      forbiddenDomainHits: domainHits,
      forbiddenGlobMatch: forbiddenGlob,
    })

    let finalRoute = route
    const rdef = f.rule
    if (rdef && rdef.minOccurrences != null && rdef.window) {
      const winMs = parseShortDuration(String(rdef.window))
      if (winMs > 0) {
        const times = f.occurrenceTimes || []
        const anchor = times.length ? Math.max(...times) : Date.now()
        const cutoff = anchor - winMs
        const occInWin = times.filter((t) => t >= cutoff).length
        if (occInWin < Number(rdef.minOccurrences)) {
          finalRoute = { fixRoute: "silent", reason: "below_min_occurrences" }
        }
      }
    }

    const allowedEditPaths = deriveAllowedPathsFromSuspected(repoRoot, signals.hitRelPaths || [], [])
    const fixRequest = buildFixRequest({
      finding: f,
      cfg,
      fixRoute: finalRoute.fixRoute,
      testPlan: testSel,
      allowedEditPaths,
      forbiddenEditPaths: [...(cfg.autofix.forbiddenPaths || [])],
      forbiddenDomainsTriggered: domainHits,
      routingReason: finalRoute.reason,
    })
    const shapeErrs = validateFixRequestShape(fixRequest)
    enrichment[f.fingerprint] = {
      fixRoute: finalRoute.fixRoute,
      routingReason: finalRoute.reason,
      testPlan: testSel,
      fixRequest,
      fixRequestValidated: shapeErrs.length === 0,
      fixRequestShapeErrors: shapeErrs,
      signals,
      advisor: { consulted: false },
    }

    const cand = finalRoute.fixRoute
    if (shouldConsultAdvisor({ cfg, runFlags: rf, candidateRoute: cand })) {
      pendingAdvisor.push({
        fingerprint: f.fingerprint,
        proposed: { fixRoute: cand, routingReason: finalRoute.reason },
        finding: f,
        fixRequest,
      })
    }
  }
  return { enrichment, pendingAdvisor }
}

function planActions({ cfg, findings, state, effects, enrichment }) {
  const plan = {
    issues: [],
    prs: [],
    agentFixes: [],
    feishu: [],
    reviewBlocks: [],
    stateMutations: [],
  }
  let templatePrBudgetUsed = 0
  let agentBudgetUsed = 0
  const maxAuto = cfg.autofix.maxPrsPerRun || 1
  const recoveryNeeded = new Set(Object.keys(state.fingerprints || {}))

  function enqueueIssueAlerts(finding, prev, recurrence, severity) {
    const hasIss = !!prev.issueNumber
    const closed = prev.issueState === "closed"
    if (!effects.canCreateIssue) return
    if (hasIss && closed) {
      plan.issues.push({
        kind: "reopen",
        number: prev.issueNumber,
        finding,
        severity,
        recurrence,
      })
    } else if (hasIss && !closed) {
      plan.issues.push({
        kind: "update",
        number: prev.issueNumber,
        finding,
        severity,
        recurrence,
      })
    } else {
      plan.issues.push({ kind: "create", finding, severity, recurrence })
    }
    plan.feishu.push({ kind: "issue_alert", finding, severity, recurrence })
  }

  function autofixAttemptsExhausted(prev, rule) {
    if (!prev.autofixFailed) return false
    const allowed = Number(rule?.maxAutofixAttempts ?? 1)
    const attempts = Number(prev.autofixAttempts ?? 1)
    return attempts >= allowed
  }

  for (const f of findings) {
    recoveryNeeded.delete(f.fingerprint)
    const prev = state.fingerprints[f.fingerprint] || {}
    const recurrence = prev.mergedFix && cfg.classification.recurrenceEscalation
    let sev = f.severity
    if (recurrence) sev = mergeSeverity(sev, "high")

    const en =
      enrichment[f.fingerprint] || {
        fixRoute: "issue_only",
        routingReason: "missing_enrichment_fallback",
        testPlan: {
          unit: [],
          integration: [],
          e2e: [],
          smoke: [],
          full: [],
          required: [],
          optional: [],
          reasons: [],
          passRule: "all-required-pass",
        },
        fixRequest: null,
      }

    const cdMs = parseShortDuration(String(f.rule?.cooldown || ""))
    const lastAct = prev.lastActionAt ? new Date(prev.lastActionAt).getTime() : 0
    const cooldownActive = cdMs > 0 && lastAct > 0 && Date.now() - lastAct < cdMs

    if (en.fixRoute === "silent" || en.routingReason === "below_min_occurrences") {
      plan.stateMutations.push({
        fingerprint: f.fingerprint,
        patch: {
          lastSeen: new Date().toISOString(),
          occurrenceCount: (prev.occurrenceCount || 0) + f.messages.length,
          severity: sev,
          missStreak: 0,
          mergedFix: prev.mergedFix || false,
          wasClosed: prev.wasClosed || false,
          issueNumber: prev.issueNumber,
          lastFixRoute: en.fixRoute,
          lastRoute: en.fixRoute,
          lastRoutingReason: en.routingReason,
        },
      })
      continue
    }

    if (en.fixRoute === "notify_only") {
      if (effects.canSendFeishu) {
        plan.feishu.push({ kind: "issue_alert", finding: f, severity: sev, recurrence })
      }
      plan.stateMutations.push({
        fingerprint: f.fingerprint,
        patch: {
          lastSeen: new Date().toISOString(),
          occurrenceCount: (prev.occurrenceCount || 0) + f.messages.length,
          severity: sev,
          missStreak: 0,
          mergedFix: prev.mergedFix || false,
          wasClosed: prev.wasClosed || false,
          issueNumber: prev.issueNumber,
          lastFixRoute: en.fixRoute,
          lastRoute: en.fixRoute,
          lastRoutingReason: en.routingReason,
        },
      })
      continue
    }

    const awaitingOpenPrMerge = !!(prev.prUrl && !prev.mergedFix)
    let automated = false

    if (cooldownActive) {
      plan.stateMutations.push({
        fingerprint: f.fingerprint,
        patch: {
          lastSeen: new Date().toISOString(),
          occurrenceCount: (prev.occurrenceCount || 0) + f.messages.length,
          severity: sev,
          missStreak: 0,
          mergedFix: prev.mergedFix || false,
          wasClosed: prev.wasClosed || false,
          issueNumber: prev.issueNumber,
          lastFixRoute: en.fixRoute,
          lastRoute: en.fixRoute,
          lastRoutingReason: `${en.routingReason || ""}|cooldown_skip`,
        },
      })
      continue
    }

    if (
      en.fixRoute === "template_patch" &&
      effects.canCreatePr &&
      templatePrBudgetUsed < maxAuto &&
      !autofixAttemptsExhausted(prev, f.rule) &&
      !awaitingOpenPrMerge
    ) {
      templatePrBudgetUsed++
      automated = true
      plan.prs.push({ finding: f, severity: sev, recurrence, enrichment: en })
      plan.reviewBlocks.push({ finding: f, severity: sev, enrichment: en })
    } else if (
      en.fixRoute === "fix_agent_request" &&
      cfg.fixAgent.enabled === true &&
      effects.canCreatePr &&
      agentBudgetUsed < maxAuto &&
      !autofixAttemptsExhausted(prev, f.rule) &&
      !prev.inProgressFix &&
      !awaitingOpenPrMerge
    ) {
      agentBudgetUsed++
      automated = true
      plan.agentFixes.push({ finding: f, severity: sev, recurrence, enrichment: en })
      plan.reviewBlocks.push({ finding: f, severity: sev, enrichment: en })
    }

    if (!automated) {
      enqueueIssueAlerts(f, prev, recurrence, sev)
    }

    plan.stateMutations.push({
      fingerprint: f.fingerprint,
      patch: {
        lastSeen: new Date().toISOString(),
        occurrenceCount: (prev.occurrenceCount || 0) + f.messages.length,
        severity: sev,
        missStreak: 0,
        mergedFix: prev.mergedFix || false,
        wasClosed: prev.wasClosed || false,
        issueNumber: prev.issueNumber,
        lastFixRoute: en.fixRoute,
        lastRoute: en.fixRoute,
        lastRoutingReason: en.routingReason,
      },
    })
  }

  const pollsToClose = cfg.classification.recoveryPollsToClose ?? 3
  for (const fp of recoveryNeeded) {
    const prev = state.fingerprints[fp] || {}
    if (!prev.issueNumber && !prev.lastSeen) continue
    const ms = (prev.missStreak || 0) + 1
    if (ms >= pollsToClose && prev.issueNumber) {
      plan.issues.push({ kind: "close", number: prev.issueNumber, fingerprint: fp, prev })
      plan.feishu.push({ kind: "recovered", fingerprint: fp, prev })
      plan.stateMutations.push({
        fingerprint: fp,
        patch: { missStreak: ms, wasClosed: true, issueNumber: null },
      })
    } else {
      plan.stateMutations.push({ fingerprint: fp, patch: { ...prev, missStreak: ms } })
    }
  }
  return plan
}

// ── 11. GitHub PR and Issue effects ────────────────────────────────────────

function githubRepoFromEnv() {
  const r = process.env.GITHUB_REPOSITORY
  if (!r) return null
  const [owner, repo] = r.split("/")
  return { owner, repo }
}

async function ghFetch(path, opts, retries) {
  const token = process.env.GITHUB_TOKEN
  if (!token) throw new Error("GITHUB_TOKEN missing")
  const url = `https://api.github.com${path}`
  const headers = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "X-GitHub-Api-Version": "2022-11-28",
  }
  let lastErr
  for (let i = 0; i <= retries; i++) {
    const res = await fetch(url, { ...opts, headers: { ...headers, ...opts?.headers } })
    if (res.ok || res.status === 404) return res
    lastErr = new Error(`GitHub ${res.status} ${await res.text()}`)
    await new Promise((r) => setTimeout(r, 500 * (i + 1)))
  }
  throw lastErr
}

function parseFingerprintFromIssueBody(body) {
  const m = String(body || "").match(/\*\*fingerprint\*\*[:\s]*`([^`\r\n]+)`/i)
  return m ? m[1].trim() : null
}

async function listLabeledIssues(gr, label, retries) {
  const out = []
  let page = 1
  for (;;) {
    const ipath = `/repos/${gr.owner}/${gr.repo}/issues?labels=${encodeURIComponent(label)}&state=all&per_page=100&page=${page}&sort=updated`
    const res = await ghFetch(ipath, { method: "GET" }, retries)
    const arr = await res.json()
    if (!Array.isArray(arr) || arr.length === 0) break
    for (const issue of arr) {
      if (issue.pull_request) continue
      out.push(issue)
    }
    if (arr.length < 100) break
    page++
    if (page > 30) break
  }
  return out
}

function pickBestIssueForFingerprint(issuesForFp) {
  let best = null
  for (const issue of issuesForFp) {
    if (!best) {
      best = issue
      continue
    }
    const rank = (iss) => (iss.state === "open" ? 2 : 1)
    if (rank(issue) > rank(best)) best = issue
    else if (rank(issue) === rank(best) && String(issue.updated_at) > String(best.updated_at)) best = issue
  }
  return best
}

async function hydrateIssueFingerprints(cfg, state) {
  const gr = githubRepoFromEnv()
  if (!gr || !process.env.GITHUB_TOKEN) return
  const retries = cfg.autofix.maxGithubRetries ?? 2
  const primaryLabel = (cfg.issues.labels && cfg.issues.labels[0]) || "ops-check"
  let issues
  try {
    issues = await listLabeledIssues(gr, primaryLabel, retries)
  } catch {
    return
  }
  const byFp = new Map()
  for (const issue of issues) {
    const fp = parseFingerprintFromIssueBody(issue.body || "")
    if (!fp) continue
    if (!byFp.has(fp)) byFp.set(fp, [])
    byFp.get(fp).push(issue)
  }
  for (const [fp, issList] of byFp) {
    const issue = pickBestIssueForFingerprint(issList)
    if (!issue) continue
    const prev = state.fingerprints[fp] || {}
    state.fingerprints[fp] = {
      ...prev,
      issueNumber: issue.number,
      issueState: issue.state === "closed" ? "closed" : "open",
      issueClosedAt: issue.closed_at || null,
    }
  }
}

async function remoteBranchExists(gr, branch, retries) {
  const rpath = `/repos/${gr.owner}/${gr.repo}/git/ref/heads/${encodeURIComponent(branch)}`
  const res = await ghFetch(rpath, { method: "GET" }, retries)
  return res.ok
}

async function refreshMergedPrFlags(cfg, state) {
  const gr = githubRepoFromEnv()
  if (!gr || !process.env.GITHUB_TOKEN) return
  const retries = cfg.autofix.maxGithubRetries ?? 2
  for (const fp of Object.keys(state.fingerprints || {})) {
    const rec = state.fingerprints[fp]
    if (!rec?.prUrl || rec.mergedFix) continue
    const m = String(rec.prUrl).match(/\/pull\/(\d+)/)
    if (!m) continue
    const num = Number(m[1])
    try {
      const res = await ghFetch(`/repos/${gr.owner}/${gr.repo}/pulls/${num}`, { method: "GET" }, retries)
      if (!res.ok) continue
      const pr = await res.json()
      if (pr.merged === true) {
        state.fingerprints[fp] = { ...rec, mergedFix: true, reviewStatus: "approved_and_merged" }
      }
    } catch {
      /* ignore */
    }
  }
}

async function createIssue({ cfg, finding, severity, recurrence, enrichment, llmStats }, retries) {
  const gr = githubRepoFromEnv()
  if (!gr) throw new Error("GITHUB_REPOSITORY not set")
  const title = `[${severity}] ${finding.service} — ${finding.msgTpl.slice(0, 80)}`
  let appendix = ""
  if (enrichment?.fixRoute) {
    appendix += `\n### routing\nfixRoute=${enrichment.fixRoute} reason=${enrichment.routingReason || ""}`
  }
  if (Array.isArray(enrichment?.fixRequestShapeErrors) && enrichment.fixRequestShapeErrors.length) {
    appendix += `\n### fix_request_validation\n${enrichment.fixRequestShapeErrors.join(", ")}`
  }
  if (enrichment?.fixRequest && enrichment.fixRoute !== "ignore_or_recover") {
    appendix += `\n### FIX REQUEST (structured)\n\n\`\`\`json\n${JSON.stringify(enrichment.fixRequest, replSet, 2).slice(0, 12000)}\n\`\`\``
  }
  if (enrichment?.testPlan?.reasons?.length) {
    appendix += `\n### test selection rationale\n${enrichment.testPlan.reasons.map((r) => `- ${r}`).join("\n")}`
  }
  if (enrichment?.agentRunnerError) {
    appendix += `\n### fix_agent_runner_last_error\n\n\`\`\`json\n${JSON.stringify(enrichment.agentRunnerError, replSet, 2).slice(0, 4000)}\n\`\`\``
  }
  if (enrichment?.agentRunnerThrown) {
    appendix += `\n### fix_agent_runner_throw\n\n\`${String(enrichment.agentRunnerThrown).slice(0, 2000)}\``
  }
  if (enrichment?.blockedReason) {
    appendix += `\n### blocked_reason\n\`${String(enrichment.blockedReason)}\`\n`
    if (enrichment?.blockedDetail) {
      appendix += `\n<details><summary>detail</summary>\n\n\`\`\`json\n${JSON.stringify(enrichment.blockedDetail, replSet, 2).slice(0, 6000)}\n\`\`\`\n</details>\n`
    }
  }
  if (llmStats && typeof llmStats === "object") {
    appendix += `\n### ops-check_llm_stats\n\`${JSON.stringify(llmStats)}\`\n`
  }
  appendix += formatAdvisorFooterLine(enrichment?.advisor)
  const body = `## ops-check

**fingerprint**: \`${finding.fingerprint}\`
**rule**: ${finding.ruleName}
**severity**: ${severity}${recurrence ? " (recurrence after fix)" : ""}
**sources**: ${[...finding.sources].join(", ")}

### samples
${finding.messages.slice(0, 5).map((m) => `- \`${m.slice(0, 200)}\``).join("\n")}
${appendix}`
  const res = await ghFetch(
    `/repos/${gr.owner}/${gr.repo}/issues`,
    {
      method: "POST",
      body: JSON.stringify({
        title,
        body,
        labels: cfg.issues.labels,
      }),
    },
    retries,
  )
  const data = await res.json()
  return data.number
}

async function updateIssue(num, bodyAppend, retries) {
  const gr = githubRepoFromEnv()
  const res = await ghFetch(`/repos/${gr.owner}/${gr.repo}/issues/${num}`, { method: "GET" }, retries)
  const cur = await res.json()
  await ghFetch(
    `/repos/${gr.owner}/${gr.repo}/issues/${num}`,
    {
      method: "PATCH",
      body: JSON.stringify({ body: `${cur.body || ""}\n\n${bodyAppend}` }),
    },
    retries,
  )
}

async function closeIssue(num, retries) {
  const gr = githubRepoFromEnv()
  await ghFetch(
    `/repos/${gr.owner}/${gr.repo}/issues/${num}`,
    {
      method: "PATCH",
      body: JSON.stringify({ state: "closed", state_reason: "completed" }),
    },
    retries,
  )
}

async function reopenIssue(num, retries) {
  const gr = githubRepoFromEnv()
  await ghFetch(
    `/repos/${gr.owner}/${gr.repo}/issues/${num}`,
    {
      method: "PATCH",
      body: JSON.stringify({ state: "open" }),
    },
    retries,
  )
}

function forbiddenPathHit(file, patterns) {
  const rel = file.replace(/\\/g, "/")
  for (const p of patterns) {
    const re = new RegExp(
      "^" +
        p
          .replace(/[.+^${}()|[\]\\]/g, "\\$&")
          .replace(/\*\*/g, ".*")
          .replace(/\*/g, "[^/]*") +
        "$",
      "i",
    )
    if (re.test(rel)) return true
  }
  return false
}

function tryBuildAutofixPatch({ finding, repoRoot }) {
  const text = finding.messages[0] || ""
  const stackTop = finding.stackTop
  if (!stackTop || stackTop === "unknown-frame") return null
  const [fpath, lineStr] = stackTop.includes(":")
    ? [stackTop.split(":")[0], stackTop.split(":")[1]]
    : [null, null]
  if (!fpath) return null
  const abs = path.isAbsolute(fpath) ? fpath : path.join(repoRoot, fpath)
  if (!fs.existsSync(abs)) return null
  const content = fs.readFileSync(abs, "utf8")
  const lineNo = Number(lineStr) || 1
  const lines = content.split(/\r?\n/)
  const idx = Math.max(0, lineNo - 1)
  const line = lines[idx] || ""
  let newLine = line
  if (/Cannot read propert(?:y|ies) of undefined/.test(text) && fpath.match(/\.(jsx?|tsx?)$/)) {
    newLine = line.replace(/(\w+)\.(\w+)/, "$1?.$2")
  } else if (
    /AttributeError: 'NoneType' object has no attribute/.test(text) &&
    fpath.match(/\.py$/)
  ) {
    if (/\.get\(/.test(line)) newLine = line.replace(/(\w+)\.get\(/, "($1 or {}).get(")
    else if (/\.\w+/.test(line)) newLine = line.replace(/(\w+)(\.\w+)/, "($1 or None)$2")
  }
  if (newLine === line) return null
  lines[idx] = newLine
  return { file: abs, content: lines.join("\n") }
}

async function createAutofixPr({ cfg, finding, repoRoot, retries, enrichment }) {
  const gr = githubRepoFromEnv()
  if (!gr) throw new Error("GITHUB_REPOSITORY not set")
  const patch = tryBuildAutofixPatch({ finding, repoRoot })
  if (!patch) return { ok: false, reason: "no patch" }

  const relPosix = path.relative(repoRoot, patch.file).replace(/\\/g, "/")
  if (forbiddenPathHit(relPosix, cfg.autofix.forbiddenPaths || [])) {
    return { ok: false, reason: "forbidden path" }
  }

  const branch = `ops-check/fix-${finding.fingerprint.slice(0, 8)}`
  if (await remoteBranchExists(gr, branch, retries)) {
    return { ok: false, reason: "branch exists on remote" }
  }

  let faCaps = {}
  try {
    if (cfg.fixAgent?.configPath) {
      const raw = await fsp.readFile(path.resolve(repoRoot, String(cfg.fixAgent.configPath)), "utf8")
      const doc = parseYamlSubset(raw)
      faCaps = doc.fixAgent || {}
    }
  } catch {
    faCaps = {}
  }

  const en = enrichment || {}
  const testSel = en.testPlan
  const forbiddenFlat = [...(cfg.autofix.forbiddenPaths || [])]
  const allowedEditPaths =
    Array.isArray(en.fixRequest?.allowedEditPaths) && en.fixRequest.allowedEditPaths.length
      ? en.fixRequest.allowedEditPaths
      : deriveAllowedPathsFromSuspected(repoRoot, en.signals?.hitRelPaths || [])

  const gitEnv = {
    ...process.env,
    GIT_AUTHOR_NAME: "ops-check",
    GIT_AUTHOR_EMAIL: "ops-check@users.noreply.github.com",
    GIT_COMMITTER_NAME: "ops-check",
    GIT_COMMITTER_EMAIL: "ops-check@users.noreply.github.com",
  }

  const iso = runIsolatedTemplatePatchPipeline({
    mainRepoRoot: repoRoot,
    branchName: branch,
    patchRelPosix: relPosix,
    patchContent: patch.content,
    testPlan: testSel,
    verificationFallback: cfg.autofix.verificationCommands || [],
    allowedEditPaths,
    forbiddenEditPaths: forbiddenFlat,
    maxDiffLines: Number(faCaps.maxDiffLines ?? 400),
    maxChangedFiles: Number(faCaps.maxChangedFiles ?? 8),
    gitEnv,
    commitMessage: `fix(ops-check): ${finding.ruleName}`,
  })

  if (!iso.ok)
    return {
      ok: false,
      reason: iso.blockedReason || iso.reason || iso.message || "isolated_patch_failed",
      blockedReason: iso.blockedReason,
      ver: iso.verification || null,
      gate: iso.gate || null,
    }

  const tok = process.env.GITHUB_TOKEN
  const remote = `https://x-access-token:${tok}@github.com/${gr.owner}/${gr.repo}.git`

  try {
    pushBranchFromWorktree({
      mainRepoRoot: repoRoot,
      worktreeRoot: iso.worktreeRoot,
      branchName: branch,
      remotePushUrl: remote,
      gitEnv,
    })
  } catch (e) {
    abortIsolatedWorktree(repoRoot, iso.worktreeRoot, branch)
    const stderr = e.stderr?.toString?.() || ""
    return {
      ok: false,
      reason: String(stderr || e.message || e),
      ver: iso.verification,
      blockedReason: "git_push_failed",
    }
  }

  const base =
    process.env.GITHUB_REF_NAME ||
    process.env.GITHUB_DEFAULT_BRANCH ||
    (() => {
      try {
        return execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
          cwd: repoRoot,
          encoding: "utf8",
        }).trim()
      } catch {
        return "main"
      }
    })()
  const fx = enrichment?.fixRequest
  const ver = iso.verification
  const prBodyParts = [
    `Template autofix (**isolated worktree**) fingerprint \`${finding.fingerprint}\`\n`,
    `### automation boundary\nPatches and verification ran only inside a disposable Git worktree; the main working tree file was **not** modified by ops-check.\n`,
    finding.msgTpl.slice(0, 500),
    `\n\n### testPlan (required = all exit 0 before PR)\n\`\`\`json\n`,
    JSON.stringify(enrichment?.testPlan || {}, replSet, 2).slice(0, 6500),
    "\n```",
    `\n### changed paths\n\`${(iso.diffNameOnly || []).join(", ")}\`\n`,
  ]
  if (fx) {
    prBodyParts.push(`\n### FIX_REQUEST_EMBED\n\`\`\`json\n`)
    prBodyParts.push(JSON.stringify(fx, replSet, 2).slice(0, 8000))
    prBodyParts.push("\n```")
  }
  const optionalFailed = !!(ver.blockedOptionalFails && ver.blockedOptionalFails.length)
  if (optionalFailed) {
    prBodyParts.push(
      `\n\n> Optional checks failed: ${ver.blockedOptionalFails.join(", ")} — opening **draft** PR for human risk review.`,
    )
  }

  const prBody = prBodyParts.join("") + formatAdvisorFooterLine(enrichment?.advisor)
  const res = await ghFetch(
    `/repos/${gr.owner}/${gr.repo}/pulls`,
    {
      method: "POST",
      body: JSON.stringify({
        title: `[ops-check] autofix ${finding.ruleName}`,
        head: branch,
        base,
        body: prBody,
        draft: optionalFailed,
      }),
    },
    retries,
  )
  const data = await res.json()
  return { ok: true, prUrl: data.html_url, branch, ver }
}

function renderReviewBlock({ finding, prUrl, verification }) {
  return `--- OPS_CHECK_REVIEW_REQUEST_BEGIN ---
pr_url: ${prUrl || "N/A"}
fingerprint: ${finding.fingerprint}
summary: ${finding.msgTpl.slice(0, 400).replace(/\n/g, " ")}
rule: ${finding.ruleName}
severity: ${finding.severity}
log_evidence: ${finding.messages[0]?.slice(0, 400)?.replace(/\n/g, " ") || ""}
patch_description: automated optional-chaining / guarded access (if applied)
verification: ${JSON.stringify(verification || [])}
--- OPS_CHECK_REVIEW_REQUEST_END ---`
}

// ── 12. Feishu card effects ───────────────────────────────────────────────

function webhookFromEnv(name) {
  return name ? process.env[name] : null
}

async function sendFeishuCard(url, payload, retries) {
  if (!url) return
  let last
  for (let i = 0; i <= retries; i++) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
    if (res.ok) return
    last = res.status
    await new Promise((r) => setTimeout(r, 400 * (i + 1)))
  }
  throw new Error(`Feishu send failed ${last}`)
}

function resolveOwnerLine(cfg, service) {
  const svc = cfg.owners?.services?.[service]?.reviewers
  const def = cfg.owners?.default?.reviewers
  const list = Array.isArray(svc) && svc.length ? svc : def
  if (!Array.isArray(list) || !list.length) return ""
  return list
    .map((r) => [r.name, r.feishu_user_id].filter(Boolean).join(":"))
    .join(", ")
}

function verificationSummaryLine(ver) {
  if (!ver?.results?.length) return ""
  return ver.results
    .map((x) => `${x.cmd} exit=${x.status}`)
    .join("; ")
    .slice(0, 500)
}

function buildCard(title, rows) {
  const md = rows.map(([k, v]) => `**${k}**: ${v}`).join("\n")
  return {
    msg_type: "interactive",
    card: {
      config: { wide_screen_mode: true },
      header: {
        title: { tag: "plain_text", content: title.slice(0, 200) },
        template: "red",
      },
      elements: [{ tag: "div", text: { tag: "lark_md", content: md.slice(0, 4000) } }],
    },
  }
}

async function maybeEscalateStalePrs({ cfg, state, effects }) {
  if (!effects.canSendFeishu) return
  const gr = githubRepoFromEnv()
  if (!gr || !process.env.GITHUB_TOKEN) return
  const minutes = cfg.notifications.escalatePrAfterMinutes ?? 60
  const cutoff = Date.now() - minutes * 60_000
  const retries = cfg.autofix.maxGithubRetries ?? 2
  const hookEsc = webhookFromEnv(cfg.notifications.escalationWebhookEnv)
  if (!hookEsc) return
  let sent = 0
  const maxF = cfg.autofix.maxFeishuPerRun ?? 20
  for (const [fp, rec] of Object.entries(state.fingerprints || {})) {
    if (sent >= maxF) break
    if (!rec?.prUrl || rec.prEscalated) continue
    const m = String(rec.prUrl).match(/\/pull\/(\d+)/)
    if (!m) continue
    const num = Number(m[1])
    const res = await ghFetch(`/repos/${gr.owner}/${gr.repo}/pulls/${num}`, { method: "GET" }, retries)
    if (!res.ok) continue
    const pr = await res.json()
    if (pr.state !== "open") continue
    const created = new Date(pr.created_at).getTime()
    if (created > cutoff) continue
    const owners = resolveOwnerLine(cfg, rec.service || "unknown-service")
    const card = buildCard("PR pending review (escalation)", [
      ["fingerprint", fp],
      ["environment", String(cfg.environment)],
      ["sources", (rec.sourceIds || "").toString()],
      ["occurrence_count", String(rec.occurrenceCount ?? "")],
      ["last_seen", String(rec.lastSeen || "")],
      ["PR", rec.prUrl],
      ["verification", verificationSummaryLine(rec.lastVerification)],
      ["recurrence", rec.mergedFix ? "post-fix recurrence tracked" : ""],
      ["owners", owners],
      ["minutes_open", String(Math.round((Date.now() - created) / 60_000))],
    ])
    await sendFeishuCard(hookEsc, card, retries)
    rec.prEscalated = true
    sent++
  }
}

async function applyGithubAndFeishu({ cfg, plan, effects, repoRoot, enrichment, llmStats }) {
  const ghRetries = cfg.autofix.maxGithubRetries ?? 2
  let feishuN = 0
  const maxF = cfg.autofix.maxFeishuPerRun ?? 20
  let issueN = 0
  const maxI = cfg.autofix.maxIssueActionsPerRun ?? 20

  const hook = webhookFromEnv(cfg.notifications.feishuWebhookEnv)
  const escHook = webhookFromEnv(cfg.notifications.escalationWebhookEnv)

  const enrichMap = enrichment || {}

  let fixAgentOverlay = null
  if (cfg.fixAgent?.configPath) {
    try {
      fixAgentOverlay = parseYamlSubset(
        await fsp.readFile(path.resolve(repoRoot, String(cfg.fixAgent.configPath)), "utf8"),
      )
    } catch {
      fixAgentOverlay = null
    }
  }
  const faCaps = fixAgentOverlay?.fixAgent || {}

  for (const agentItem of plan.agentFixes || []) {
    if (!effects.canCreatePr) continue
    const en = agentItem.enrichment
    const fx = en?.fixRequest
    if (!fx || !fx.fingerprint) continue
    const gr = githubRepoFromEnv()
    const branch = `ops-check/fix-${fx.fingerprint.slice(0, 8)}`
    writeFixRequestArtifact(path.join(repoRoot, ".ops-check", "last-fix-requests"), fx.fingerprint, fx)

    const gitEnv = {
      ...process.env,
      GIT_AUTHOR_NAME: "ops-check",
      GIT_AUTHOR_EMAIL: "ops-check@users.noreply.github.com",
      GIT_COMMITTER_NAME: "ops-check",
      GIT_COMMITTER_EMAIL: "ops-check@users.noreply.github.com",
    }
    const forbiddenFlat = [...(cfg.autofix.forbiddenPaths || [])]
    const allowedEditPaths =
      Array.isArray(fx.allowedEditPaths) && fx.allowedEditPaths.length
        ? fx.allowedEditPaths
        : deriveAllowedPathsFromSuspected(repoRoot, en.signals?.hitRelPaths || [])

    try {
      if (gr && (await remoteBranchExists(gr, branch, ghRetries))) {
        if (effects.canCreateIssue && issueN < maxI) {
          const num = await createIssue(
            {
              cfg,
              finding: agentItem.finding,
              severity: agentItem.severity,
              recurrence: agentItem.recurrence,
              enrichment: {
                ...en,
                blockedReason: "remote_branch_already_exists_for_fingerprint",
                autofixFailed: true,
              },
              llmStats,
            },
            ghRetries,
          )
          agentItem.finding._issueNumber = num
          agentItem.finding._autofixFailed = true
          agentItem.finding._blockedReason = "remote_branch_already_exists_for_fingerprint"
          issueN++
        }
        continue
      }

      const isolate = await runIsolatedAgentFixPipeline({
        mainRepoRoot: repoRoot,
        branchName: branch,
        fixAgentCfg: fixAgentOverlay,
        fingerprint: fx.fingerprint,
        simulate: !!(cfg.fixAgent && cfg.fixAgent.simulateRunner),
        timeoutMs: (cfg.fixAgent?.timeoutMinutes || 30) * 60_000,
        testPlan: en.testPlan,
        verificationFallback: cfg.autofix.verificationCommands || [],
        allowedEditPaths,
        forbiddenEditPaths: forbiddenFlat,
        maxDiffLines: Number(faCaps.maxDiffLines ?? 400),
        maxChangedFiles: Number(faCaps.maxChangedFiles ?? 8),
        gitEnv,
        fixPayload: fx,
      })

      if (!isolate.ok) {
        const detailPayload = isolate.agentOutcome || isolate.gate || isolate.verification || isolate
        if (effects.canCreateIssue && issueN < maxI) {
          const num = await createIssue(
            {
              cfg,
              finding: agentItem.finding,
              severity: agentItem.severity,
              recurrence: agentItem.recurrence,
              enrichment: {
                ...en,
                blockedReason: isolate.blockedReason || "agent_fix_blocked",
                blockedDetail: detailPayload,
                ...(isolate.agentOutcome && !isolate.agentOutcome.ok
                  ? { agentRunnerError: isolate.agentOutcome }
                  : {}),
                autofixFailed: true,
              },
              llmStats,
            },
            ghRetries,
          )
          agentItem.finding._issueNumber = num
          agentItem.finding._autofixFailed = true
          agentItem.finding._blockedReason = isolate.blockedReason
          issueN++
        }
        continue
      }

      if (!process.env.GITHUB_TOKEN || !gr) {
        if (effects.canCreateIssue && issueN < maxI) {
          const num = await createIssue(
            {
              cfg,
              finding: agentItem.finding,
              severity: agentItem.severity,
              recurrence: agentItem.recurrence,
              enrichment: {
                ...en,
                blockedReason: "GITHUB_TOKEN_missing",
                autofixFailed: true,
              },
              llmStats,
            },
            ghRetries,
          )
          agentItem.finding._issueNumber = num
          issueN++
        }
        abortIsolatedWorktree(repoRoot, isolate.worktreeRoot, branch)
        continue
      }

      const tok = process.env.GITHUB_TOKEN
      const remote = `https://x-access-token:${tok}@github.com/${gr.owner}/${gr.repo}.git`

      try {
        pushBranchFromWorktree({
          mainRepoRoot: repoRoot,
          worktreeRoot: isolate.worktreeRoot,
          branchName: branch,
          remotePushUrl: remote,
          gitEnv,
        })
      } catch (e) {
        abortIsolatedWorktree(repoRoot, isolate.worktreeRoot, branch)
        if (effects.canCreateIssue && issueN < maxI) {
          const num = await createIssue(
            {
              cfg,
              finding: agentItem.finding,
              severity: agentItem.severity,
              recurrence: agentItem.recurrence,
              enrichment: {
                ...en,
                blockedReason: "git_push_failed",
                blockedDetail: String(e.message || e),
                autofixFailed: true,
              },
              llmStats,
            },
            ghRetries,
          )
          agentItem.finding._issueNumber = num
          issueN++
        }
        continue
      }

      const base =
        process.env.GITHUB_REF_NAME ||
        process.env.GITHUB_DEFAULT_BRANCH ||
        (() => {
          try {
            return execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
              cwd: repoRoot,
              encoding: "utf8",
            }).trim()
          } catch {
            return "main"
          }
        })()
      const ver = isolate.verification
      const optionalFailed = !!(ver?.blockedOptionalFails && ver.blockedOptionalFails.length)
      const bodyParts = [
        `Bounded **Fix Agent** path via isolated worktree fingerprint \`${fx.fingerprint}\`\n`,
        `### routing\nroute=${en.fixRoute || "?"} reason=${en.routingReason || ""}\n`,
        `### test selection\n${(en.testPlan?.reasons || []).map((x) => `- ${x}`).join("\n") || "_"}\n`,
        `\n### test results\n\`\`\`\n${verificationSummaryLine(ver)}\n\`\`\`\n`,
        `\n### diff paths\n${(isolate.diffNameOnly || []).join(", ")}\n`,
      ]
      bodyParts.push(`\n### FIX REQUEST\n\`\`\`json\n${JSON.stringify(fx, replSet, 2).slice(0, 12000)}\n\`\`\``)
      if (optionalFailed)
        bodyParts.push(
          `\n> Optional checks failed: ${ver.blockedOptionalFails.join(", ")} — **draft PR** for human judgment.`,
        )
      bodyParts.push(
        `\n### risk boundary\nEdits gated by allowed path globs and max diff/file counts; reviewer must approve; ops-check never merges.`,
      )

      const res = await ghFetch(
        `/repos/${gr.owner}/${gr.repo}/pulls`,
        {
          method: "POST",
          body: JSON.stringify({
            title: `[ops-check] agent fix ${agentItem.finding.ruleName}`,
            head: branch,
            base,
            body: bodyParts.join(""),
            draft: optionalFailed,
          }),
        },
        ghRetries,
      )
      const data = await res.json()
      agentItem.finding._prUrl = data.html_url
      agentItem.finding._lastVerification = ver
      console.log(
        "--- OPS_CHECK_AGENT_REPORT ---",
        JSON.stringify(
          {
            fingerprint: fx.fingerprint,
            diff: isolate.diffNameOnly,
            verification: ver?.results?.slice?.(0, 40),
          },
          replSet,
          2,
        ),
        "--- OPS_CHECK_AGENT_REPORT_END ---",
      )
      console.log(
        renderReviewBlock({
          finding: agentItem.finding,
          prUrl: data.html_url,
          verification: ver?.results,
        }),
      )
      if (effects.canSendFeishu && feishuN < maxF && hook) {
        const occ = agentItem.finding.messages?.length ?? 0
        const owners = resolveOwnerLine(cfg, agentItem.finding.service)
        const card = buildCard(`${agentItem.severity} ${agentItem.finding.service}`, [
          ["fingerprint", agentItem.finding.fingerprint],
          ["environment", String(cfg.environment)],
          ["sources", [...agentItem.finding.sources].join(",")],
          ["occurrence_count", String(occ)],
          ["last_seen", new Date().toISOString()],
          ["PR", data.html_url],
          ["Issue", ""],
          ["verification", verificationSummaryLine(ver)],
          ["recurrence", agentItem.recurrence ? "yes" : ""],
          ["owners", owners],
        ])
        await sendFeishuCard(hook, card, 2)
        feishuN++
      }
    } catch (e) {
      if (effects.canCreateIssue && issueN < maxI) {
        const num = await createIssue(
          {
            cfg,
            finding: agentItem.finding,
            severity: agentItem.severity,
            recurrence: agentItem.recurrence,
            enrichment: {
              ...en,
              blockedReason: "agent_isolation_throw",
              agentRunnerThrown: String(e.message || e),
              autofixFailed: true,
            },
            llmStats,
          },
          ghRetries,
        )
        issueN++
        agentItem.finding._issueNumber = num
      }
    }
  }

  for (const prReq of plan.prs) {
    if (!effects.canCreatePr) continue
    const r = await createAutofixPr({
      cfg,
      finding: prReq.finding,
      repoRoot,
      retries: ghRetries,
      enrichment: prReq.enrichment,
    })
    if (r.ok && r.prUrl) {
      prReq.finding._prUrl = r.prUrl
      prReq.finding._lastVerification = r.ver
      console.log(renderReviewBlock({ finding: prReq.finding, prUrl: r.prUrl, verification: r.ver?.results }))
      if (effects.canSendFeishu && feishuN < maxF && hook) {
        const occ = prReq.finding.messages?.length ?? 0
        const owners = resolveOwnerLine(cfg, prReq.finding.service)
        const card = buildCard(`${prReq.severity} ${prReq.finding.service}`, [
          ["fingerprint", prReq.finding.fingerprint],
          ["environment", String(cfg.environment)],
          ["sources", [...prReq.finding.sources].join(",")],
          ["occurrence_count", String(occ)],
          ["last_seen", new Date().toISOString()],
          ["PR", r.prUrl],
          ["Issue", ""],
          ["verification", verificationSummaryLine(r.ver)],
          ["recurrence", prReq.recurrence ? "yes" : ""],
          ["owners", owners],
        ])
        await sendFeishuCard(hook, card, 2)
        feishuN++
      }
    } else {
      if (effects.canCreateIssue && issueN < maxI) {
        prReq.finding._autofixFailed = true
        prReq.finding._blockedReason = r.blockedReason || r.reason || "template_pr_failed"
        const num = await createIssue(
          {
            cfg,
            finding: prReq.finding,
            severity: prReq.severity,
            recurrence: prReq.recurrence,
            enrichment: {
              ...(prReq.enrichment || {}),
              blockedReason: r.blockedReason || r.reason,
              blockedDetail: { gate: r.gate || null, verification: r.ver || null },
              autofixFailed: true,
            },
            llmStats,
          },
          ghRetries,
        )
        issueN++
        prReq.finding._issueNumber = num
      }
    }
  }

  for (const is of plan.issues) {
    if (!effects.canCreateIssue || issueN >= maxI) continue
    const en = is.finding ? enrichMap[is.finding.fingerprint] : null
    if (is.kind === "create") {
      const num = await createIssue(
        {
          cfg,
          finding: is.finding,
          severity: is.severity,
          recurrence: is.recurrence,
          enrichment: en,
          llmStats,
        },
        ghRetries,
      )
      is.finding._issueNumber = num
      issueN++
    } else if (is.kind === "update" && is.number) {
      await updateIssue(
        is.number,
        `\n_Update ${new Date().toISOString()}_: still seen; count+ sources=${[...is.finding.sources].join(",")}`,
        ghRetries,
      )
      issueN++
    } else if (is.kind === "reopen" && is.number) {
      await reopenIssue(is.number, ghRetries)
      await updateIssue(
        is.number,
        `\n_Reopened ${new Date().toISOString()}_: recurrence after previous close; sources=${[...is.finding.sources].join(",")}`,
        ghRetries,
      )
      issueN++
    } else if (is.kind === "close" && is.number) {
      await closeIssue(is.number, ghRetries)
      issueN++
    }
  }

  for (const f of plan.feishu) {
    if (!effects.canSendFeishu || feishuN >= maxF) continue
    let use = hook
    if (f.kind === "escalation") use = escHook
    if (!use) continue
    if (f.kind === "issue_alert") {
      const occ = f.finding.messages?.length ?? 0
      const owners = resolveOwnerLine(cfg, f.finding.service)
      const extra = []
      if (f.finding._prUrl) extra.push(["PR", f.finding._prUrl])
      if (f.finding._issueNumber) extra.push(["Issue", `#${f.finding._issueNumber}`])
      const card = buildCard(`${f.severity} ${f.finding.service}`, [
        ["fingerprint", f.finding.fingerprint],
        ["environment", String(cfg.environment)],
        ["sources", [...f.finding.sources].join(",")],
        ["occurrence_count", String(occ)],
        ["last_seen", new Date().toISOString()],
        ["message_excerpt", f.finding.msgTpl.slice(0, 200)],
        ["verification", ""],
        ["recurrence", f.recurrence ? "yes" : ""],
        ["owners", owners],
        ...extra,
      ])
      await sendFeishuCard(use, card, 2)
      feishuN++
    } else if (f.kind === "recovered") {
      const owners = resolveOwnerLine(cfg, f.prev?.service || cfg.project || "unknown-service")
      const card = buildCard(`recovered ${f.fingerprint.slice(0, 12)}`, [
        ["fingerprint", f.fingerprint],
        ["environment", String(cfg.environment)],
        ["Issue", String(f.prev.issueNumber || "")],
        ["occurrence_count", String(f.prev.occurrenceCount ?? "")],
        ["last_seen", String(f.prev.lastSeen || "")],
        ["missStreak", String(f.prev.missStreak || "")],
        ["verification", ""],
        ["recurrence", ""],
        ["owners", owners],
      ])
      await sendFeishuCard(use, card, 2)
      feishuN++
    }
  }
}

// ── 13. main() ─────────────────────────────────────────────────────────────

async function main() {
  const argv = parseArgs(process.argv)
  const repoRoot = process.cwd()
  let configPath =
    argv.config ||
    (fs.existsSync(path.join(repoRoot, "ops-check", "config.yaml"))
      ? path.join(repoRoot, "ops-check", "config.yaml")
      : path.join(repoRoot, "ops-check", "config.example.yaml"))

  let cfg
  try {
    cfg = await loadConfig(configPath)
  } catch (e) {
    console.error("config load error:", e.message)
    process.exit(1)
  }

  try {
    cfg = await resolveCicdLogSourceRefs(cfg, repoRoot)
  } catch (e) {
    console.error("config resolve error:", e.message)
    process.exit(1)
  }

  const diagnoseMode = argv.cmd === "diagnose"
  const planMode = argv.cmd === "plan"
  const sandboxPlanOnly =
    diagnoseMode || planMode || argv.dryRunFlag === true || cfg.runtime?.dryRun === true

  /** Planning step uses these flags — dry-run-like surfaces without mutating trackers */
  const plannerEffects = {
    dryRun: sandboxPlanOnly,
    planningOnlySandbox: sandboxPlanOnly,
    canWriteState: false,
    canSendFeishu: false,
    /** PR/Issue intents are modeled; actual GH calls still blocked outside live `run`. */
    canCreatePr:
      sandboxPlanOnly &&
      (argv.cmd === "run" || planMode || diagnoseMode) &&
      (cfg.autofix.enabled === true || cfg.fixAgent?.enabled === true),
    canCreateIssue: sandboxPlanOnly && (argv.cmd === "run" || planMode || diagnoseMode),
  }

  /** Live mutations only apply for real CI/local `run` without sandbox */
  const liveRun = argv.cmd === "run" && !sandboxPlanOnly
  const applyEffects = {
    dryRun: !liveRun,
    planningOnlySandbox: sandboxPlanOnly,
    canWriteState: liveRun,
    canSendFeishu: liveRun,
    canCreatePr:
      liveRun &&
      (cfg.autofix.enabled === true || cfg.fixAgent?.enabled === true),
    canCreateIssue: liveRun,
  }

  const effectsForPlanner = sandboxPlanOnly ? plannerEffects : applyEffects

  const schemaErrs = validateConfig(cfg, { forRun: argv.cmd === "run" && !argv.dryRunFlag })

  if (schemaErrs.length) {
    console.error("CONFIG ERRORS:\n", schemaErrs.join("\n"))
    const sendCfgErrCard = liveRun
    if (sendCfgErrCard) {
      const hook = webhookFromEnv(cfg.notifications.feishuWebhookEnv)
      if (hook) {
        try {
          await sendFeishuCard(
            hook,
            buildCard("ops-check config error", [["errors", schemaErrs.join("; ").slice(0, 1500)]]),
            2,
          )
        } catch {
          /* ignore */
        }
      }
    }
    process.exit(2)
  }

  if (argv.cmd === "validate-config") {
    console.log(JSON.stringify({ ok: true, configPath: path.relative(repoRoot, configPath) }, null, 2))
    process.exit(0)
  }

  if (argv.cmd === "validate-test-map") {
    const rel = cfg.testMapPath ?? "ops-check/test-map.example.yaml"
    const doc =
      rel &&
      (await loadTestMap({
        testMapPath: rel,
        repoRoot,
        parseYamlSubset,
      }))
    if (!doc) {
      console.error("test-map load failed:", rel)
      process.exit(2)
    }
    const disc = await discoverE2E(repoRoot, doc)
    console.log(JSON.stringify({ ok: true, testMap: rel, e2eDiscovery: disc }, null, 2))
    process.exit(0)
  }

  const rulesPath = path.join(path.dirname(configPath), "rules.yaml")
  const rulesRaw = await fsp.readFile(
    fs.existsSync(rulesPath) ? rulesPath : path.join(repoRoot, "ops-check", "rules.yaml"),
    "utf8",
  )
  const rules = loadRulesDoc(rulesRaw)
  const ruleErrs = validateRules(rules)
  if (ruleErrs.length) {
    console.error("rules.yaml validation errors:\n" + ruleErrs.map((e) => "  - " + e).join("\n"))
    process.exit(2)
  }
  const rulesActive = rules.filter((r) => r.enabled !== false)

  const stateFile = path.resolve(repoRoot, cfg.runtime.stateFile || ".ops-check/state.json")
  const state = await readState(stateFile)
  state.cursors = state.cursors || {}
  state.fingerprints = state.fingerprints || {}

  if (!sandboxPlanOnly) {
    await hydrateIssueFingerprints(cfg, state)
    await refreshMergedPrFlags(cfg, state)
  }

  const until = new Date()

  const fetchers = buildFetcherRegistry()
  const allEntries = []
  const nextCursors = {}
  for (const source of cfg.logSources) {
    const fetcher = fetchers[source.type]
    if (!fetcher) throw new Error(`Unsupported log source: ${source.type}`)
    const cursor = sandboxPlanOnly ? null : state.cursors[source.id]
    let sourceSince = null
    if (diagnoseMode || planMode) {
      const ms = parseDuration(argv.since || "30m")
      sourceSince = new Date(Date.now() - ms)
    } else {
      const winMin = source.queryWindowMinutes ?? cfg.defaults?.queryWindowMinutes ?? 10
      sourceSince = new Date(Date.now() - winMin * 60_000)
    }
    let result
    try {
      result = await fetcher({
        since: sourceSince,
        until,
        cursor,
        limit: source.limit ?? cfg.defaults.logLimit,
        source,
        sharedConfig: cfg,
      })
    } catch (e) {
      console.error(`fetcher ${source.id} error:`, e.message)
      if (argv.cmd === "run" && !sandboxPlanOnly) process.exit(3)
      result = { entries: [], nextCursor: null }
    }
    allEntries.push(...result.entries)
    if (result.nextCursor) nextCursors[source.id] = result.nextCursor
    else nextCursors[source.id] = state.cursors[source.id] ?? null
  }

  const entries = normalizeAndSortEntries(allEntries)
  for (const e of entries) {
    e.message = redactText(e.message)
  }

  const usedLlm = { count: 0 }
  const {
    findings: findingsList,
    entryRows,
    llmStats,
    llmVerdictsDelta,
    llmDailyUsageNext,
  } = await analyzePipeline({
    cfg,
    entries,
    rules: rulesActive,
    environment: cfg.environment || "unknown",
    project: cfg.project || "unknown",
    diagnoseMode,
    usedLlm,
    prevLlmVerdicts: state.llmVerdicts || {},
    nowMs: Date.now(),
    llmDailyUsageInitial: state.llmDailyUsage || { date: "", count: 0 },
  })

  if (applyEffects.canWriteState) {
    state.llmVerdicts = { ...(state.llmVerdicts || {}), ...llmVerdictsDelta }
    state.llmDailyUsage = llmDailyUsageNext
  }

  const interimState = structuredClone(state)
  const testMapPathConfigured = cfg.testMapPath ?? "ops-check/test-map.example.yaml"
  const testMapDoc = await loadTestMap({
    testMapPath: testMapPathConfigured,
    repoRoot,
    parseYamlSubset,
  })
  const runFlags = {
    advisorAllowed:
      cfg.routingAdvisor?.enabled === true && (!sandboxPlanOnly || argv.enableAdvisorFlag === true),
  }

  const { enrichment, pendingAdvisor } = buildFingerprintEnrichment({
    cfg,
    findings: findingsList,
    state: interimState,
    testMapDoc,
    repoRoot,
    runFlags,
  })

  const {
    stats: routingAdvisorStats,
    advisorVerdictsDelta,
  } = await consultAdvisorsAndReroute({
    cfg,
    findings: findingsList,
    enrichment,
    pendingAdvisor,
    runFlags,
    state,
    nowMs: Date.now(),
    llmDailyUsage: llmDailyUsageNext,
  })

  if (applyEffects.canWriteState && advisorVerdictsDelta && Object.keys(advisorVerdictsDelta).length) {
    state.advisorVerdicts = { ...(state.advisorVerdicts || {}), ...advisorVerdictsDelta }
  }

  const plan = planActions({
    cfg,
    findings: findingsList,
    state: interimState,
    effects: effectsForPlanner,
    enrichment,
  })

  /** @type {string[]} */
  const sideEffectsSkipped = []
  if (sandboxPlanOnly)
    sideEffectsSkipped.push(
      "github_issues",
      "github_pull_requests",
      "git_push",
      "feishu_cards",
      "state_file_writes",
    )
  if (cfg.fixAgent?.enabled !== true) sideEffectsSkipped.push("cursor_fix_agent_spawn")

  const findingSummaries = findingsList.map((f) => ({
    fingerprint: f.fingerprint,
    service: f.service,
    severity: f.severity,
    fixRoute: enrichment[f.fingerprint]?.fixRoute,
    routingReason: enrichment[f.fingerprint]?.routingReason ?? null,
    plannedAction: plannedActionLabel(f.fingerprint, plan),
    testPlan: enrichment[f.fingerprint]?.testPlan || null,
    fixRequestEmbedded: !!enrichment[f.fingerprint]?.fixRequest,
    sideEffectsSkipped: sandboxPlanOnly ? [...sideEffectsSkipped] : [],
  }))

  console.log(
    JSON.stringify(
      {
        mode: argv.cmd,
        sandboxPlanOnly,
        entries: entries.length,
        findings: findingsList.length,
        planned: {
          templatePrs: plan.prs.length,
          agentFixAttempts: plan.agentFixes?.length || 0,
          issues: plan.issues.length,
          feishu: plan.feishu.length,
        },
        plannerEffectsUsed: effectsForPlanner,
        sideEffectsSkipped,
        findingsPlan: findingSummaries,
        llmStats,
        routingAdvisorStats,
      },
      null,
      2,
    ),
  )

  if (sandboxPlanOnly) {
    printDiagnosticSummary({ cfg, entryRows, plan, enrichment })
    console.log(
      "--- OPS_CHECK_MATURE_PREVIEW_BEGIN ---",
      JSON.stringify({ plan, enrichment, findingsPlan: findingSummaries }, replSet, 2),
      "--- OPS_CHECK_MATURE_PREVIEW_END ---",
    )
    process.exit(0)
  }

  await applyGithubAndFeishu({ cfg, plan, effects: applyEffects, repoRoot, enrichment, llmStats })

  await maybeEscalateStalePrs({ cfg, state, effects: applyEffects })

  for (const m of plan.stateMutations) {
    state.fingerprints[m.fingerprint] = { ...(state.fingerprints[m.fingerprint] || {}), ...m.patch }
  }
  state.cursors = nextCursors
  for (const pr of plan.prs) {
    const fp = pr.finding.fingerprint
    if (pr.finding._prUrl) {
      state.fingerprints[fp] = {
        ...state.fingerprints[fp],
        prUrl: pr.finding._prUrl,
        prCreatedAt: new Date().toISOString(),
        lastActionAt: new Date().toISOString(),
        reviewStatus: "pending_or_timeout",
        service: pr.finding.service,
        sourceIds: [...pr.finding.sources].join(","),
        lastVerification: pr.finding._lastVerification || null,
      }
    } else if (pr.finding._autofixFailed) {
      const p = state.fingerprints[fp] || {}
      state.fingerprints[fp] = {
        ...p,
        autofixFailed: true,
        autofixAttempts: (p.autofixAttempts || 0) + 1,
        blockedReason: pr.finding._blockedReason || "",
        inProgressFix: false,
      }
    }
  }
  for (const ag of plan.agentFixes || []) {
    const fp = ag.finding.fingerprint
    if (ag.finding._prUrl) {
      state.fingerprints[fp] = {
        ...state.fingerprints[fp],
        prUrl: ag.finding._prUrl,
        fixedPr: ag.finding._prUrl,
        prCreatedAt: new Date().toISOString(),
        lastActionAt: new Date().toISOString(),
        reviewStatus: "pending_or_timeout",
        service: ag.finding.service,
        sourceIds: [...ag.finding.sources].join(","),
        lastVerification: ag.finding._lastVerification || null,
        inProgressFix: false,
      }
    } else if (ag.finding._autofixFailed) {
      const p = state.fingerprints[fp] || {}
      state.fingerprints[fp] = {
        ...p,
        autofixFailed: true,
        autofixAttempts: (p.autofixAttempts || 0) + 1,
        blockedReason: ag.finding._blockedReason || "",
        inProgressFix: false,
      }
    }
  }
  for (const is of plan.issues) {
    const fp = is.finding?.fingerprint
    if (!fp) continue
    if (is.kind === "create" && is.finding?._issueNumber) {
      state.fingerprints[fp] = {
        ...(state.fingerprints[fp] || {}),
        issueNumber: is.finding._issueNumber,
        issueState: "open",
        lastActionAt: new Date().toISOString(),
      }
    }
    if ((is.kind === "update" || is.kind === "reopen") && is.number) {
      state.fingerprints[fp] = {
        ...(state.fingerprints[fp] || {}),
        issueNumber: is.number,
        issueState: "open",
      }
    }
  }
  await writeState(stateFile, state, { canWriteState: applyEffects.canWriteState })
}

export {
  buildFingerprintEnrichment,
  consultAdvisorsAndReroute,
  applyAdvisorBatchSync,
  formatAdvisorFooterLine,
}

function replSet(key, value) {
  if (value instanceof Set) return [...value]
  return value
}

const __filename = fileURLToPath(import.meta.url)
const invoked = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename)
if (invoked) {
  main().catch((e) => {
    console.error(e)
    process.exit(1)
  })
}
