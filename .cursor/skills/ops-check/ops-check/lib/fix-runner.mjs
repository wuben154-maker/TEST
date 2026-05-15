/**
 * Bounded Fix Agent Runner + isolated worktree autofix pipeline.
 */

import fs from "node:fs"
import path from "node:path"
import crypto from "node:crypto"
import { spawnSync, execFileSync } from "node:child_process"
import process from "node:process"
import { runTieredVerification } from "./verification-tier.mjs"
import { runChatCompletionsFixAgent } from "./fix-chat-api.mjs"

/**
 * Validates diff/size hints after an agent hypothetically modified the tree.
 * @param {{
 * repoRoot: string,
 * baselineNameOnly: string[],
 * baselineStat: Record<string,string>,
 * maxDiffLines: number,
 * maxChangedFiles: number,
 * allowedEditPaths: string[],
 * forbiddenEditPaths: string[],
 * }} ctx
 */
export function assertBoundedDiffGate(ctx) {
  const {
    maxDiffLines = 400,
    maxChangedFiles = 8,
    allowedEditPaths = [],
    forbiddenEditPaths = [],
  } = ctx
  /** @type {string[]} */
  let nameOnlyLines = []
  try {
    const out = spawnSync("git", ["diff", "--name-only"], {
      cwd: ctx.repoRoot,
      encoding: "utf8",
    })
    nameOnlyLines = String(out.stdout || "")
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)
  } catch {
    return { ok: false, reason: "git_diff_name_only_failed" }
  }

  if (nameOnlyLines.length > maxChangedFiles) {
    return { ok: false, reason: `too_many_files:${nameOnlyLines.length}`, nameOnlyLines }
  }

  let statPatch
  try {
    const out = spawnSync("git", ["diff"], { cwd: ctx.repoRoot, encoding: "utf8" })
    statPatch = String(out.stdout || "")
  } catch {
    return { ok: false, reason: "git_diff_failed" }
  }

  const lineCount = statPatch.split(/\r?\n/).length
  if (lineCount > maxDiffLines) {
    return { ok: false, reason: `diff_too_large_lines:${lineCount}` }
  }

  for (const rel of nameOnlyLines) {
    const n = rel.replace(/\\/g, "/")
    if (n.includes("..")) return { ok: false, reason: "path_traversal" }
    if (forbiddenEditPaths.some((p) => matchesGlobLit(n, p))) {
      return { ok: false, reason: `forbidden_hit:${n}` }
    }
    if (allowedEditPaths.length && !allowedEditPaths.some((p) => matchesGlobLit(n, p))) {
      return { ok: false, reason: `outside_allowed:${n}` }
    }
  }

  const addedBinary = nameOnlyLines.filter((fn) =>
    /\.(png|jpg|gif|webp|exe|dll|jar|zip|wasm)$/i.test(fn),
  )
  if (addedBinary.length) return { ok: false, reason: "binary_blocked" }

  return { ok: true, lineCount, nameOnlyLines }
}

/** Very small matcher for ** globs consistent with planner forbidden paths style */
function matchesGlobLit(relPosix, globPat) {
  const rx =
    "^" +
    globPat
      .replace(/\\/g, "/")
      .replace(/[.+^${}()|[\]\\]/g, "\\$&")
      .replace(/\*\*/g, ".*")
      .replace(/\*/g, "[^/]*") +
    "$"
  return new RegExp(rx, "i").test(relPosix.replace(/\\/g, "/"))
}

/** Default allowlist conservative for Watchtower repos */
export function deriveAllowedPathsFromSuspected(_repoRoot, suspectedRel, extra = []) {
  const rels = [...(suspectedRel || []), ...(extra || [])]
    .map((x) => String(x || "").trim().replace(/\\/g, "/").replace(/^\.?\//, ""))
    .filter(Boolean)

  /** @returns {string} */
  const dirnamePosix = (r) => {
    const ix = r.lastIndexOf("/")
    return ix === -1 ? "" : r.slice(0, ix)
  }

  /** @type {Set<string>} */
  const scopes = new Set()
  if (!rels.length) return []
  for (const r of rels) {
    if (r.includes("*")) scopes.add(`${r}`)
    else {
      const d = dirnamePosix(r)
      scopes.add(`${d}/**`)
    }
  }
  return [...scopes]
}

export function writeFixRequestArtifact(dir, fingerprint, payload) {
  fs.mkdirSync(dir, { recursive: true })
  const fpShort = fingerprint.slice(0, 16)
  const p = path.join(dir, `fix-request-${fpShort}.json`)
  fs.writeFileSync(p, JSON.stringify(payload, null, 2), "utf8")
  return p
}

/**
 * Executes configured cursor-agent / Claude CLI / generic command (sync spawn).
 *
 * @param {{
 * repoRoot: string,
 * fixRequestPath: string,
 * fixAgentCfg?: any,
 * timeoutMs?: number,
 * simulate?: boolean,
 * }} args
 */
export function runCliConfiguredFixAgent(args) {
  const { repoRoot, fixRequestPath, fixAgentCfg, timeoutMs = 30 * 60_000, simulate = false } = args
  const fa = fixAgentCfg?.fixAgent || fixAgentCfg || {}
  const command = fa.command || "cursor-agent"
  const cliArgsTpl = fa.args || ["run", "--input", "{{fixRequestPath}}"]
  const apiUrl = fa.api?.endpointEnv ? process.env[fa.api.endpointEnv] : null
  const apiTok = fa.api?.tokenEnv ? process.env[fa.api.tokenEnv] : null

  const hasApi = !!(apiUrl && apiTok && String(apiTok).trim())
  const hasDashboardApiKey = !!String(process.env.CURSOR_API_KEY || "").trim()
  const hasAnthropicApiKey = !!String(process.env.ANTHROPIC_API_KEY || "").trim()
  let hasCli = false
  try {
    const r = spawnSync(command, ["--help"], { encoding: "utf8", timeout: 7000 })
    const helpBlob = String(r.stderr || "") + String(r.stdout || "")
    hasCli =
      r.status === 0 ||
      /usage|cursor|claude code|print mode|--print/i.test(helpBlob)
  } catch {
    hasCli = false
  }

  if (!hasApi && !hasDashboardApiKey && !hasAnthropicApiKey && !hasCli) {
    return {
      ok: false,
      code: "runner_deps_missing",
      message:
        "Fix Agent runner not runnable: install the configured CLI on PATH (e.g. cursor-agent or claude), set CURSOR_API_KEY and/or ANTHROPIC_API_KEY as applicable, or set both overlay api.endpointEnv + api.tokenEnv.",
    }
  }

  if (simulate) {
    return {
      ok: false,
      code: "simulated_runner_noop",
      message: "Simulation — did not invoke agent CLI/API.",
    }
  }

  /** @type {string[]} */
  const argv = cliArgsTpl.map((a) => String(a).replaceAll("{{fixRequestPath}}", fixRequestPath))
  try {
    const r = spawnSync(command, argv, {
      cwd: repoRoot,
      encoding: "utf8",
      timeout: timeoutMs,
      env: { ...process.env, OPS_CHECK_FIX_INPUT: fixRequestPath },
    })
    if (r.status === 0) return { ok: true, stdout: r.stdout?.slice?.(-6000), stderr: r.stderr?.slice?.(-6000) }
    return {
      ok: false,
      code: `agent_exit_${r.status}`,
      stderr: r.stderr?.slice?.(-6000),
      stdout: r.stdout?.slice?.(-6000),
    }
  } catch (e) {
    return { ok: false, code: "spawn_error", message: String(e.message || e) }
  }
}

/**
 * Fix Agent entry: OpenAI-compatible chat when `fixAgent.chatApi` is set; else CLI spawn.
 *
 * @param {{
 * repoRoot: string,
 * fixRequestPath: string,
 * fixAgentCfg?: any,
 * timeoutMs?: number,
 * simulate?: boolean,
 * }} args
 * @returns {Promise<{ ok: boolean, [k: string]: any }>}
 */
export async function runConfiguredFixAgent(args) {
  const { repoRoot, fixRequestPath, fixAgentCfg, timeoutMs = 30 * 60_000, simulate = false } = args
  const fa = fixAgentCfg?.fixAgent || fixAgentCfg || {}
  const chatRaw = fa.chatApi
  if (chatRaw?.baseUrl && chatRaw?.apiKeyEnv) {
    const chat = {
      ...chatRaw,
      maxChangedFiles: Number(chatRaw.maxChangedFiles ?? fa.maxChangedFiles ?? 8),
      model: chatRaw.model || process.env.OPENAI_MODEL || undefined,
    }
    const apiKey = process.env[chat.apiKeyEnv]
    if (!String(apiKey || "").trim()) {
      return {
        ok: false,
        code: "runner_deps_missing",
        message: `Missing env ${chat.apiKeyEnv} for fixAgent.chatApi`,
      }
    }
    if (simulate) {
      return {
        ok: false,
        code: "simulated_runner_noop",
        message: "Simulation — did not invoke chat Fix Agent.",
      }
    }
    return runChatCompletionsFixAgent(repoRoot, fixRequestPath, chat, timeoutMs)
  }
  return runCliConfiguredFixAgent(args)
}

// ── Isolated worktree pipeline (template_patch + agent) ────────────────────

export function isInsideGitRepo(dir) {
  const r = spawnSync("git", ["rev-parse", "--is-inside-work-tree"], { cwd: dir, encoding: "utf8" })
  return r.status === 0 && String(r.stdout || "").trim() === "true"
}

export function resolveGitBaseRef(mainRepoRoot) {
  const envRef = process.env.GITHUB_SHA || process.env.GITHUB_REF
  let ref = ""
  try {
    if (process.env.GITHUB_REF_NAME && process.env.GITHUB_REF_NAME !== "") {
      ref = process.env.GITHUB_REF_NAME
    } else if (envRef?.startsWith("refs/heads/")) {
      ref = envRef.slice("refs/heads/".length)
    } else {
      ref = execFileSync("git", ["rev-parse", "HEAD"], { cwd: mainRepoRoot, encoding: "utf8" }).trim()
    }
  } catch {
    ref = "HEAD"
  }
  return ref || "HEAD"
}

function teardownWorktreeOnly(mainRepoRoot, worktreePath) {
  if (!worktreePath || !fs.existsSync(worktreePath)) return
  try {
    execFileSync("git", ["worktree", "remove", "--force", worktreePath], {
      cwd: mainRepoRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    })
  } catch {
    /* best-effort */
  }
}

function deleteLocalBranch(mainRepoRoot, branchName) {
  try {
    execFileSync("git", ["branch", "-D", branchName], {
      cwd: mainRepoRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    })
  } catch {
    /* ignore */
  }
}

/**
 * @param {{
 * mainRepoRoot: string,
 * branchName: string,
 * baseRef: string,
 * }} args
 */
export function prepareIsolatedWorktree(args) {
  const { mainRepoRoot, branchName, baseRef } = args
  const rnd = crypto.randomBytes(4).toString("hex")
  const safeBn = branchName.replace(/[^\w\-/]+/g, "_").replace(/\//g, "_")
  const worktreeRoot = path.join(mainRepoRoot, ".ops-check", "worktrees", `${safeBn}-${rnd}`)
  fs.mkdirSync(path.dirname(worktreeRoot), { recursive: true })

  try {
    execFileSync(
      "git",
      ["worktree", "add", "--detach", worktreeRoot, baseRef],
      { cwd: mainRepoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    )
  } catch (e) {
    try {
      fs.rmSync(worktreeRoot, { recursive: true, force: true })
    } catch (_) {
      /* */
    }
    return { ok: false, blockedReason: "worktree_prepare_failed", message: String(e.message || e) }
  }

  try {
    execFileSync(
      "git",
      ["checkout", "-b", branchName],
      { cwd: worktreeRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    )
  } catch (e) {
    teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
    try {
      fs.rmSync(worktreeRoot, { recursive: true, force: true })
    } catch (_) {
      /* */
    }
    if (String(e.message || "").includes("already exists"))
      return { ok: false, blockedReason: "local_branch_already_exists", message: String(e.message || e) }
    return { ok: false, blockedReason: "checkout_new_branch_failed", message: String(e.message || e) }
  }

  return { ok: true, worktreeRoot }
}

/**
 * Template autofix with patch applied only inside disposable worktree; runs diff gate + required tests there.
 *
 * Does not create GitHub PR.
 *
 * @param {{
 * mainRepoRoot: string,
 * branchName: string,
 * patchRelPosix: string,
 * patchContent: string,
 * testPlan: any,
 * verificationFallback: string[],
 * allowedEditPaths: string[],
 * forbiddenEditPaths: string[],
 * maxDiffLines?: number,
 * maxChangedFiles?: number,
 * gitEnv: Record<string,string>,
 * commitMessage?: string,
 * }} args
 */
export function runIsolatedTemplatePatchPipeline(args) {
  const {
    mainRepoRoot,
    branchName,
    patchRelPosix,
    patchContent,
    testPlan,
    verificationFallback,
    allowedEditPaths,
    forbiddenEditPaths,
    maxDiffLines = 400,
    maxChangedFiles = 8,
    gitEnv,
    commitMessage = "fix(ops-check): template patch",
  } = args

  if (!isInsideGitRepo(mainRepoRoot))
    return { ok: false, blockedReason: "not_a_git_repository" }

  const baseRef = resolveGitBaseRef(mainRepoRoot)
  const wt = prepareIsolatedWorktree({ mainRepoRoot, branchName, baseRef })
  if (!wt.ok) return wt

  const worktreeRoot = wt.worktreeRoot
  const target = path.join(worktreeRoot, patchRelPosix.replace(/^\.?\/?/, "").replace(/\//g, path.sep))

  try {
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, patchContent, "utf8")

    let diffBeforeLines = ""
    try {
      const d0 = spawnSync("git", ["diff", "--name-only"], {
        cwd: worktreeRoot,
        encoding: "utf8",
      })
      diffBeforeLines = String(d0.stdout || "")
        .trim()
        .split(/\r?\n/)
        .filter(Boolean)
        .join(",")
    } catch {
      diffBeforeLines = ""
    }

    const gate = assertBoundedDiffGate({
      repoRoot: worktreeRoot,
      allowedEditPaths,
      forbiddenEditPaths,
      maxDiffLines,
      maxChangedFiles,
    })

    /** @type {string[]} */
    const nameOnlyAfter = [...(gate.ok ? gate.nameOnlyLines || [] : [])]
    if (!gate.ok) {
      deleteLocalBranch(mainRepoRoot, branchName)
      teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
      return {
        ok: false,
        blockedReason: "diff_gate_failed",
        gate,
        diffNameOnly: nameOnlyAfter,
        verification: null,
        gitMeta: { branchName, baseRef, diffBeforeNameOnlyCsv: diffBeforeLines },
      }
    }

    if (!gate.nameOnlyLines?.length) {
      deleteLocalBranch(mainRepoRoot, branchName)
      teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
      return {
        ok: false,
        blockedReason: "no_git_diff_after_patch",
        gate,
        verification: null,
      }
    }

    const verification = runTieredVerification(testPlan, verificationFallback || [], worktreeRoot)

    if (!verification.requiredOk) {
      deleteLocalBranch(mainRepoRoot, branchName)
      teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
      return {
        ok: false,
        blockedReason: "required_tests_failed",
        gate,
        verification,
        diffNameOnly: nameOnlyAfter,
        gitMeta: { branchName, baseRef },
      }
    }

    execFileSync("git", ["add", "--", patchRelPosix.replace(/^\.?\/?/, "").replace(/\\/g, "/")], {
      cwd: worktreeRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: gitEnv,
    })
    execFileSync("git", ["commit", "-m", commitMessage], {
      cwd: worktreeRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: gitEnv,
    })

    return {
      ok: true,
      blockedReason: null,
      gate,
      verification,
      diffNameOnly: nameOnlyAfter,
      worktreeRoot,
      gitMeta: { branchName, baseRef },
      optionalFails: verification.blockedOptionalFails || [],
    }
  } catch (e) {
    deleteLocalBranch(mainRepoRoot, branchName)
    teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
    return { ok: false, blockedReason: "template_pipeline_exception", message: String(e.message || e) }
  }
}

/**
 * After runIsolatedTemplatePatchPipeline succeeds: push branch from worktree then remove link.
 *
 * Caller must discard worktree on push failure manually or call teardown helpers.
 *
 * @param {{
 * mainRepoRoot: string,
 * worktreeRoot: string,
 * branchName: string,
 * remotePushUrl?: string | null,
 * gitEnv?: Record<string,string>,
 * }} ctx
 */
export function pushBranchFromWorktree(ctx) {
  const { mainRepoRoot, worktreeRoot, branchName, remotePushUrl, gitEnv = {} } = ctx
  if (!remotePushUrl) throw new Error("remotePushUrl required for push")
  execFileSync("git", ["push", "-q", remotePushUrl, `HEAD:${branchName}`], {
    cwd: worktreeRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ...gitEnv },
  })
  teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
}

/** Remove worktree (and try to delete branch) after failed push recovery */
export function abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName) {
  if (branchName) deleteLocalBranch(mainRepoRoot, branchName)
  if (worktreeRoot) teardownWorktreeOnly(mainRepoRoot, worktreeRoot)
}

/**
 * Agent path inside isolated worktree: run CLI/API, gate diff, run tests, commit changes.
 *
 * @param {{
 * mainRepoRoot: string,
 * branchName: string,
 * fixAgentCfg?: any,
 * fixAgentOverlayPath?: string,
 * fingerprint: string,
 * simulate?: boolean,
 * timeoutMs: number,
 * testPlan: any,
 * verificationFallback: string[],
 * allowedEditPaths: string[],
 * forbiddenEditPaths: string[],
 * maxDiffLines?: number,
 * maxChangedFiles?: number,
 * gitEnv: Record<string,string>,
 * commitMessage?: string,
 * runner?: (a: any) => Promise<any> | any,
 * fixPayload: any,
 * }} args
 */
export async function runIsolatedAgentFixPipeline(args) {
  const {
    mainRepoRoot,
    branchName,
    fixAgentCfg,
    fingerprint,
    simulate,
    timeoutMs,
    testPlan,
    verificationFallback,
    allowedEditPaths,
    forbiddenEditPaths,
    maxDiffLines = 400,
    maxChangedFiles = 8,
    gitEnv,
    commitMessage = "fix(ops-check): bounded agent patch",
    runner = runConfiguredFixAgent,
    fixPayload,
  } = args

  if (!isInsideGitRepo(mainRepoRoot))
    return { ok: false, blockedReason: "not_a_git_repository", agentOutcome: null }

  const baseRef = resolveGitBaseRef(mainRepoRoot)
  const wt = prepareIsolatedWorktree({ mainRepoRoot, branchName, baseRef })
  if (!wt.ok)
    return { ok: false, blockedReason: wt.blockedReason || "worktree_prepare_failed", agentOutcome: null }

  const worktreeRoot = wt.worktreeRoot

  try {
    const fxDir = path.join(worktreeRoot, ".ops-check", "last-fix-requests")
    const payload = fixPayload
    if (!payload?.fingerprint) {
      abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName)
      return { ok: false, blockedReason: "missing_fix_payload", agentOutcome: null }
    }
    const fixPath = writeFixRequestArtifact(fxDir, fingerprint, payload)

    const agentOutcome = await Promise.resolve(
      runner({
        repoRoot: worktreeRoot,
        fixRequestPath: fixPath,
        fixAgentCfg,
        simulate: !!simulate,
        timeoutMs,
      }),
    )

    if (!agentOutcome.ok) {
      const code = agentOutcome.code || ""
      const br =
        code === "simulated_runner_noop"
          ? "runner_simulated_skip"
          : code === "runner_deps_missing"
            ? "runner_deps_missing"
            : "agent_execution_failed"

      abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName)
      return {
        ok: false,
        blockedReason: br,
        agentOutcome,
        gate: null,
        verification: null,
      }
    }

    const gate = assertBoundedDiffGate({
      repoRoot: worktreeRoot,
      allowedEditPaths,
      forbiddenEditPaths,
      maxDiffLines,
      maxChangedFiles,
    })

    /** @type {string[]} */
    const nameOnly = gate.ok ? [...(gate.nameOnlyLines || [])] : []
    const verification = runTieredVerification(testPlan, verificationFallback || [], worktreeRoot)

    if (!gate.ok) {
      abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName)
      return {
        ok: false,
        blockedReason: "diff_gate_failed",
        agentOutcome,
        gate,
        verification,
      }
    }

    if (!nameOnly.length) {
      abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName)
      return {
        ok: false,
        blockedReason: "agent_no_file_changes",
        agentOutcome,
        gate,
        verification,
      }
    }

    if (!verification.requiredOk) {
      abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName)
      return {
        ok: false,
        blockedReason: "required_tests_failed",
        agentOutcome,
        gate,
        verification,
      }
    }

    execFileSync("git", ["add", "-A"], {
      cwd: worktreeRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: gitEnv,
    })
    execFileSync("git", ["commit", "-m", commitMessage], {
      cwd: worktreeRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: gitEnv,
    })

    return {
      ok: true,
      blockedReason: null,
      agentOutcome,
      gate,
      verification,
      diffNameOnly: nameOnly,
      worktreeRoot,
      gitMeta: { branchName, baseRef },
      optionalFails: verification.blockedOptionalFails || [],
    }
  } catch (e) {
    abortIsolatedWorktree(mainRepoRoot, worktreeRoot, branchName)
    return {
      ok: false,
      blockedReason: "agent_pipeline_exception",
      message: String(e.message || e),
      agentOutcome: null,
    }
  }
}
